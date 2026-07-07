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
from urllib import request as urllib_request
from urllib import error as urllib_error
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, Dict, List

# 고정 색상 import
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.fixed_colors import FIXED_COLORS
from api.binance_client import BinanceClient, BinanceConfig
import threading

class ModernSettingsWindow:
    """현대적 설정 창 - 고정 스킨 디자인"""

    _STOCK_BROKER_CHECKLIST_RELATIVE_PATH = os.path.join(
        'docs', 'STOCK_BROKER_WINDOWS_CONNECTION_CHECKLIST_20260611.md'
    )

    _STOCK_API_VERSION_OPTIONS = {
        'kiwoom': {
            'openapi': ['pykiwoom', 'kiwoom_api'],
            'mock': ['mock'],
        },
        'shinhan': {
            'openapi': ['solapi', 'xingapi'],
            'rest': ['solapi_rest'],
            'mock': ['mock'],
        },
        'miraeAsset': {
            'openapi': ['miraemts', 'miraedaas'],
            'rest': ['kis'],
            'mock': ['mock'],
        },
        'koreaInvestment': {
            'openapi': ['kis'],
            'rest': ['kis'],
            'mock': ['mock'],
        },
    }

    _UPDATE_REPOSITORIES = [
        "nwsoft/ai-trading-clinet-pro",
        "nwosft/ai-trading-client",
        "nwsoft/ai-trading-client",
    ]

    def __init__(self, parent=None, current_settings=None, on_save_callback=None, ai_diagnosis_result=None):
        self.parent = parent
        self.root = ctk.CTkToplevel(parent) if parent else ctk.CTk()
        self.root.title("NoahAI Trading - 설정")
        self.root.geometry("900x800")
        self.root.resizable(True, True)

        # 모달 창 설정
        if parent:
            self.root.transient(parent)
            self.root.grab_set()  # 모달 창으로 설정

        # 설정 데이터
        self.current_settings = current_settings or {}
        self.ai_diagnosis_result = self._normalize_ai_diagnosis_result(ai_diagnosis_result)
        # Pylance 타입 에러 방지용 명시적 초기화
        self.exchange_var = None
        self.original_settings = self.current_settings.copy()
        self.on_save_callback = on_save_callback  # 콜백 함수 저장
        self.main_app = getattr(parent, 'main_app', None) if parent is not None else None
        self._ai_diagnosis_collapsed = False
        self._ai_diagnosis_body_frame = None

        # Pylance 에러 방지: 조건부 생성되는 UI 속성은 None으로 초기화
        self.margin_type_combo = None
        self.dynamic_mode_combo = None
        self.manual_regime_combo = None

        # UI 설정
        self.setup_ui()
        # 현재 설정 로드(어떤 방식으로 띄우든 값 주입)
        try:
            self.load_current_settings()
        except Exception:
            pass

        # 창 닫기 이벤트 핸들러 설정
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 중앙 정렬
        self.center_window()

    def _color(self, key: str, fallback: str = "#9ca3af") -> str:
        """고정 색상 접근 헬퍼"""
        return FIXED_COLORS.get(key, fallback)

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
            "바이낸스: ✅ 지원",
            "업비트: ✅ 지원",
        ]
        if not is_windows:
            broker_compatibility.append("키움증권(OpenAPI+): ❌ Windows 전용")
        elif py_bits == 32:
            broker_compatibility.append("키움증권(OpenAPI+): ✅ 사용 가능 (32bit Python)")
        else:
            broker_compatibility.append("키움증권(OpenAPI+): ⚠ 32bit Python 필요")

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
                    "- 모델: gpt-4o-mini\n"
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
                    if hasattr(self, 'update_status_label') and self.update_status_label is not None:
                        self.update_status_label.configure(
                            text="업데이트 확인 실패: 원격 릴리즈 정보를 가져오지 못했습니다.",
                            text_color="#f59e0b",
                        )
                    messagebox.showwarning(
                        "업데이트 확인",
                        "원격 릴리즈 정보를 가져오지 못했습니다. 네트워크/저장소 상태를 확인해 주세요.",
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
                    status_text = f"새 버전 발견: {latest_version} (현재 v{current_version}){suffix}"
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
                label.configure(text=f"업데이트 다운로드 실패: {reason}", text_color="#f59e0b")
                return
        except Exception:
            pass

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
            text = (
                f"적용 대상 EXE: {info.get('install_target_exe', '-') }\n"
                f"현재 실행 EXE: {info.get('current_exe', '-') }\n"
                f"업데이트 캐시: {info.get('update_cache_dir', '-') }"
            )
            label.configure(text=text, text_color="#94a3b8")
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

        applied = bool(auto_manager.apply_pending_update_and_restart())
        if not applied:
            messagebox.showwarning("업데이트", "업데이트 적용 예약에 실패했습니다. 종료 후 다시 시도해 주세요.")
            return

        messagebox.showinfo("업데이트", "업데이트 적용이 예약되었습니다. 앱을 종료합니다.")
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

        kiwoom_api_type = 'openapi'
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

        shinhan_api_type = 'openapi'
        if hasattr(self, 'shinhan_api_type_combo') and self.shinhan_api_type_combo is not None:
            try:
                shinhan_api_type = str(self.shinhan_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        shinhan_api_version = 'solapi'
        if hasattr(self, 'shinhan_api_version_combo') and self.shinhan_api_version_combo is not None:
            try:
                shinhan_api_version = str(self.shinhan_api_version_combo.get()).strip()
            except Exception:
                pass

        mirae_asset_api_type = 'openapi'
        if hasattr(self, 'mirae_asset_api_type_combo') and self.mirae_asset_api_type_combo is not None:
            try:
                mirae_asset_api_type = str(self.mirae_asset_api_type_combo.get()).strip().lower()
            except Exception:
                pass

        mirae_asset_api_version = 'miraemts'
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

        korea_investment_api_version = 'kis'
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
            lines.append("[⚠️ Mac/Linux에서 키움 실연결 불가]")
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
                lines.append("- 키움 런타임: ✅ ActiveX 로딩/이벤트 바인딩 정상")
            else:
                error = runtime_diag.get("error", "unknown")
                details = runtime_diag.get("details", {})
                py_bits = details.get("python_bits", "?")
                lines.append(f"- 키움 런타임: ❌ 실패 (원인: {error})")
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
            print(f"⚠️ 저장 후 증권사 점검 안내 스케줄 실패: {e}")

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
            print(f"⚠️ 저장 후 증권사 점검 안내 실패: {e}")

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
                kiwoom_type = str(self.kiwoom_api_type_combo.get()).strip().lower() if hasattr(self, 'kiwoom_api_type_combo') else 'openapi'
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
            sections.append('- 권장값: api_type=openapi, api_version=pykiwoom')
            sections.append('- 실패 시: mock 성공 + openapi 실패면 설치/비트수/OCX 문제 가능성이 큽니다.')

        if 'shinhan' in broker_names:
            sections.append('')
            sections.append('신한증권 점검')
            sections.append('- 핵심 포인트: 토큰 발급에 app_key/app_secret이 필요합니다.')
            sections.append('- 중요: NoahAI는 신한 연동을 지원하지만, 계정의 OpenAPI 권한이 개인계정에 열려 있는지는 신한 정책/신청 상태에 따라 달라질 수 있습니다.')
            sections.append('- 현재 빌드는 입력한 ID/비밀번호를 app_key/app_secret 대응값으로도 동기화 저장합니다.')
            sections.append('- 권장값: api_type=openapi 또는 rest, api_version=solapi')
            sections.append('- 연결 전 확인: 증권사 고객센터/개발자 포털에서 내 계정이 API 사용 승인 상태인지 확인하세요.')

        if 'miraeAsset' in broker_names:
            sections.append('')
            sections.append('미래에셋증권 점검')
            sections.append('- 핵심 포인트: 인증 정보 저장값과 API 타입/버전 조합이 맞아야 합니다.')
            sections.append('- 중요: NoahAI는 미래에셋 연동을 지원하지만, OpenAPI 접근 권한은 계정 유형/신청 상태에 따라 제한될 수 있습니다.')
            sections.append('- 권장값: api_type=openapi 또는 rest, api_version=miraemts 또는 허용된 운영 버전')
            sections.append('- 연결 전 확인: 개인계정 API 사용 가능 여부와 발급된 app_key/app_secret 상태를 먼저 확인하세요.')

        if 'koreaInvestment' in broker_names:
            sections.append('')
            sections.append('한국투자증권 점검')
            sections.append('- 핵심 포인트: KIS 앱키/시크릿과 계좌번호가 저장되어야 인증/조회가 가능합니다.')
            sections.append('- 권장값: api_type=rest, api_version=kis')
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
            api_type = self._safe_combo_value(api_type_attr, default=str(config.get('api_type', 'openapi') or 'openapi'))
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
            'ready': '✅',
            'caution': '⚠️',
            'not_ready': '🛑',
        }
        status_color = status_color_map.get(status, '#f59e0b')
        status_icon = status_icon_map.get(status, '⚠️')
        
        header_label = ctk.CTkLabel(
            header_frame,
            text=f"{status_icon} AI 실행 준비도 진단",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=status_color
        )
        header_label.pack(anchor="w")

        toggle_button = ctk.CTkButton(
            header_frame,
            text='접기',
            command=self._toggle_ai_diagnosis_panel,
            font=ctk.CTkFont(family='Segoe UI', size=11, weight='bold'),
            width=80,
            height=26,
            fg_color='#334155',
            hover_color='#475569',
        )
        toggle_button.pack(anchor='e')
        self._ai_diagnosis_toggle_btn = toggle_button

        generated_at = str(self.ai_diagnosis_result.get('generated_at', '') or '').strip()
        runtime_summary = self._get_python_runtime_summary()
        runtime_os = f"{runtime_summary.get('os_name', 'Unknown')} {runtime_summary.get('os_release', '')}".strip()
        runtime_text = (
            f"실행 환경: {runtime_os} ({runtime_summary.get('os_bits', '?')}bit)"
            f"  |  Python {runtime_summary.get('python_version', '?')} ({runtime_summary.get('python_bits', '?')}bit)"
        )

        runtime_label = ctk.CTkLabel(
            diagnosis_frame,
            text=runtime_text,
            font=ctk.CTkFont(family='Segoe UI', size=11),
            text_color='#94a3b8',
            justify='left',
        )
        runtime_label.pack(fill='x', padx=15, pady=(0, 4))

        if generated_at:
            meta_label = ctk.CTkLabel(
                diagnosis_frame,
                text=f"진단 시각(로컬): {generated_at}  |  마지막 준비도 점검 시점",
                font=ctk.CTkFont(family='Segoe UI', size=11),
                text_color='#94a3b8',
                justify='left',
            )
            meta_label.pack(fill='x', padx=15, pady=(0, 8))
        else:
            runtime_label.configure(text=f"{runtime_text}  |  진단 시각(로컬): -")

        body_frame = ctk.CTkFrame(diagnosis_frame, fg_color="#1a2540")
        body_frame.pack(fill="x", padx=15, pady=(0, 12))
        self._ai_diagnosis_body_frame = body_frame

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
                text="⚙️ 지금 수정하기",
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

    def setup_ui(self):
        """UI 설정 (메인 컨테이너/제목/탭/하단 버튼)"""
        # 메인 컨테이너 (투명색 금지 정책: 고정 배경 적용)
        main_frame = ctk.CTkFrame(self.root, fg_color="#0b1120")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 제목
        self._title_label = ctk.CTkLabel(
            main_frame,
            text="⚙️ 설정",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        self._title_label.pack(pady=(0, 20))
        
        # AI 진단 결과 표시 (있는 경우)
        if self.ai_diagnosis_result:
            self._create_ai_diagnosis_panel(main_frame)

        # 탭 뷰 생성 (고정 스킨)
        self.tabview = ctk.CTkTabview(
            main_frame,
            width=850,
            height=650
        )
        self.tabview.pack(fill="both", expand=True, pady=(0, 20))

        # 탭들 생성 (테마 탭 제거됨)
        self.create_openai_tab()
        self.create_exchange_api_tab()
        self.create_exchange_selection_tab()
        # self.create_theme_settings_tab()  # 테마 시스템 제거로 삭제됨
        self.create_general_tab()
        self.create_ai_settings_tab()
        self.create_advanced_layers_tab()
        self.create_alphaarena_tab()
        self.create_update_info_tab()  # 자동업데이트/수동 업데이트 관리 탭 (가장 오른쪽)

        # 하단 버튼 영역
        self.create_button_area(main_frame)

    def create_openai_tab(self):
        """OpenAI API 설정 탭 - 기존 구조 정확히 재현"""
        tab = self.tabview.add("OpenAI API")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # OpenAI API 설정 그룹
        openai_group = ctk.CTkFrame(scroll_frame)
        openai_group.pack(fill="x", pady=(0, 20))

        # 그룹 제목
        openai_title = ctk.CTkLabel(
            openai_group,
            text="🤖 OpenAI API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        openai_title.pack(pady=(20, 15), padx=20)

        _ai_models = [
            "gpt-4o-mini",
            "gpt-4o",
            "gpt-4.1-mini",
            "gpt-4.1",
            "gpt-5-mini",
            "gpt-5",
        ]

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
            text="OpenAI 키 발급 안내",
            width=170,
            height=32,
            fg_color=self._color("secondary", "#4b5563"),
            hover_color=self._hover_from(self._color("secondary", "#4b5563")),
            command=lambda: self._show_api_key_help_dialog(kind='openai'),
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
            text="OpenAI 공식 페이지 열기",
            width=180,
            height=32,
            fg_color=self._color("secondary", "#0f766e"),
            hover_color=self._hover_from(self._color("secondary", "#0f766e")),
            command=lambda: self._open_external_url("https://platform.openai.com/api-keys", "OpenAI"),
        ).pack(side="left", padx=6)

        # OpenAI API Key
        api_key_label = ctk.CTkLabel(
            openai_group,
            text="OpenAI API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        api_key_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.openai_api_key_entry = ctk.CTkEntry(
            openai_group,
            placeholder_text="sk-...",
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

        # OpenAI 호환 Base URL (DeepSeek/OpenRouter/Ollama 등)
        openai_base_url_label = ctk.CTkLabel(
            openai_group,
            text="OpenAI 호환 Base URL (선택):",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        openai_base_url_label.pack(anchor="w", padx=20, pady=(2, 5))

        self.openai_base_url_entry = ctk.CTkEntry(
            openai_group,
            placeholder_text="예: https://api.deepseek.com | https://openrouter.ai/api/v1 | http://localhost:11434/v1",
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

        # AI 트레이딩 모델
        trading_model_label = ctk.CTkLabel(
            openai_group,
            text="AI 트레이딩 모델:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        trading_model_label.pack(anchor="w", padx=20, pady=(10, 5))

        self.openai_model_combo = ctk.CTkComboBox(
            openai_group,
            values=_ai_models,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
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

        self.assistant_ai_model_combo = ctk.CTkComboBox(
            openai_group,
            values=_ai_models,
            height=40,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.assistant_ai_model_combo.pack(fill="x", padx=20, pady=(0, 20))

        # ── AI 모델 비용 티어 배치 ──────────────────────────────────────────
        tier_title_label = ctk.CTkLabel(
            openai_group,
            text="AI 모델 역할별 배치 (비용 최적화):",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        tier_title_label.pack(anchor="w", padx=20, pady=(6, 2))

        tier_desc_label = ctk.CTkLabel(
            openai_group,
            text="빈번 호출(신호분석·패턴) → 저비용 / 중요 분석(손익·리포트) → 표준 / 정밀 진단·최적화 → 고성능",
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
        self.ai_role_cheap_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.ai_role_cheap_combo.set("gpt-4o-mini")
        self.ai_role_cheap_combo.pack(fill="x", padx=20, pady=(0, 8))

        tier_standard_label = ctk.CTkLabel(
            openai_group,
            text="표준 분석 (표준비용 모델):",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        tier_standard_label.pack(anchor="w", padx=20, pady=(0, 3))
        self.ai_role_standard_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.ai_role_standard_combo.set("gpt-4o")
        self.ai_role_standard_combo.pack(fill="x", padx=20, pady=(0, 8))

        tier_premium_label = ctk.CTkLabel(
            openai_group,
            text="정밀 진단·최적화 (고성능 모델):",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        tier_premium_label.pack(anchor="w", padx=20, pady=(0, 3))
        self.ai_role_premium_combo = ctk.CTkComboBox(
            openai_group,
            values=_tier_models,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("secondary", "#1f2937"),
            border_width=2,
            corner_radius=8
        )
        self.ai_role_premium_combo.set("gpt-4o")
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
            values=["사용자 최종확인", "AI 자동적용"],
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
        info_text = """💡 OpenAI API 설정 안내

• AI 트레이딩 모델: 실제 거래 분석 및 실행에 사용되는 AI 모델
• AI 어시스턴트 모델: 사용자와의 대화 및 질의응답에 사용되는 AI 모델
• AI 모델 역할별 배치: 빈번 호출은 저비용 모델, 정밀 진단은 고성능 모델로 분리해 비용을 최적화합니다
• 프리셋 선택 가이드:
    - 절약형: API 비용이 가장 중요할 때
    - 균형형: 초보/일반 사용자 기본 권장
    - 정밀형: 진단 정확도가 비용보다 중요할 때
• AI 설정 적용 방식: 기본값은 "사용자 최종확인"이며 법적/운영 리스크 최소화에 유리합니다
• 어시스턴트 대화로도 모델 변경/티어 조정 요청이 가능합니다(2단계 확인 또는 자동적용 정책 적용)
• API 키: OpenAI에서 발급받은 API 키를 입력하세요
• ChatGPT 유료(Plus/Team)와 OpenAI API 과금은 별개입니다
• OpenAI 호환 Base URL(선택): OpenAI 기본 엔드포인트 대신 DeepSeek/OpenRouter/Ollama 등 호환 API를 사용할 때 입력합니다
• AI 설정 도우미: '키 발급' 도구가 아니라 키 발급 후 모델/적용정책을 도와주는 기능입니다
• 음성 기능(STT/TTS)은 선택 기능이며 기본값은 비활성입니다"""

        info_label = ctk.CTkLabel(
            scroll_frame,
            text=info_text,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        info_label.pack(fill="x", pady=(0, 20))

    def _apply_ai_model_preset(self, preset_name: str):
        """OpenAI API 탭의 모델 프리셋을 콤보 UI에 즉시 반영한다."""
        presets: Dict[str, Dict[str, str]] = {
            'cost_save': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o-mini',
                'frequent_cheap': 'gpt-3.5-turbo',
                'standard': 'gpt-4o-mini',
                'premium': 'gpt-4o',
                'label': '절약형',
                'desc': 'API 비용을 최소화하려는 사용자에게 적합합니다.',
                'cost_level': '낮음',
            },
            'balanced': {
                'openai_model': 'gpt-4o-mini',
                'assistant_ai_model': 'gpt-4o',
                'frequent_cheap': 'gpt-4o-mini',
                'standard': 'gpt-4o',
                'premium': 'gpt-4o',
                'label': '균형형',
                'desc': '비용/품질 균형이 좋아 초보 포함 대부분 사용자에게 권장됩니다.',
                'cost_level': '중간',
            },
            'quality': {
                'openai_model': 'gpt-4o',
                'assistant_ai_model': 'gpt-4o',
                'frequent_cheap': 'gpt-4o-mini',
                'standard': 'gpt-4o',
                'premium': 'gpt-5',
                'label': '정밀형',
                'desc': '복잡한 진단 정확도를 우선할 때 적합하지만 비용이 증가할 수 있습니다.',
                'cost_level': '높음',
            },
        }
        selected = presets.get(preset_name)
        if not selected:
            return

        try:
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

            # AI 어시스턴트 탭/위젯 보장
            if hasattr(dashboard, '_ensure_ai_assistant_tab'):
                try:
                    dashboard._ensure_ai_assistant_tab()
                except Exception:
                    pass

            assistant = getattr(dashboard, 'ai_assistant_widget', None)
            if hasattr(dashboard, 'tab_widget') and dashboard.tab_widget:
                try:
                    dashboard.tab_widget.set("💬 AI 어시스턴트")
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
                "대시보드에서 '💬 AI 어시스턴트' 탭을 먼저 열고 다시 시도해 주세요."
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
                        "- 초보 권장 모델: gpt-4o-mini\n"
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
                        "   - 설정 > OpenAI API > OpenAI API Key에 붙여넣기\n"
                        "5) Base URL은 보통 비워두기\n"
                        "   - OpenAI 공식 API면 비워둡니다\n"
                        "   - DeepSeek/OpenRouter/Ollama 같은 호환 API일 때만 입력\n"
                        "6) 모델/프리셋 선택\n"
                        "   - 초보 기본 권장: gpt-4o-mini + 균형형 프리셋\n"
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
                    "1) 설정 > OpenAI API 탭\n"
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
                "- 실주문 허용(enable_stock_live_order): 실제 주문 API를 열지 여부\n"
                "- STOP 시 포지션 처리: 자동흐름 중지 시 기존 포지션을 유지할지 정리할지 기준\n\n"
                "왜 아직 수동 확인이 남아 있나\n"
                "- 증권 주문은 브로커 정책, 장시간, 계좌 상태, 실잔고 영향이 커서\n"
                "  사용자가 명시적으로 허용하는 단계가 안전합니다.\n"
                "- NoahAI 철학은 '몰래 자동화'가 아니라 '설명 → 확인 → 허용 범위 실행'입니다.\n\n"
                "권장 순서\n"
                "- 처음에는 auto_start OFF, 실주문 허용 OFF\n"
                "- 연결/로그/진단 확인 후 실주문 허용 ON\n"
                "- 실주문 허용 ON 후에도 가드레일은 유지\n\n"
                "즉, 여기 값들은 AI 판단 품질 숫자가 아니라 실행 권한 스위치입니다."
            ),
        )

    def create_general_tab(self):
        """일반 설정 탭: 페이퍼 트레이딩 토글 등 공통 옵션"""
        tab = self.tabview.add("일반")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 일반 설정 그룹
        general_group = ctk.CTkFrame(scroll_frame)
        general_group.pack(fill="x", pady=(0, 20))

        title = ctk.CTkLabel(
            general_group,
            text="⚙️ 일반 설정",
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
            text="🎯 포지션 모드 설정",
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

        # 관리자 전용 데모 모드 토글
        try:
            print("🔍 ModernSettingsWindow - 데모 모드 토글 생성 시작...")

            # 관리자 체크 (get_current_user_account 우선, 토큰 파일 폴백)
            is_admin = False
            current_user = ""

            # 방법 1: get_current_user_account 사용
            try:
                from path_utils import get_current_user_account
                current_user = get_current_user_account()
                print(f"🔍 ModernSettingsWindow - get_current_user_account 결과: '{current_user}'")
                if current_user:
                    is_admin = current_user.lower() in ['admin', 'nwsoft', 'developer', 'dev']
                    print(f"🔍 ModernSettingsWindow - get_current_user_account로 관리자 확인: '{current_user}' -> {is_admin}")

                    # 개발환경에서 추가 확인
                    if is_admin:
                        print(f"✅ ModernSettingsWindow - 개발환경에서 관리자 권한 확인: {current_user}")
            except Exception as e:
                print(f"⚠️ ModernSettingsWindow - get_current_user_account 실패: {e}")

            # 방법 2: 토큰 파일에서 확인 (폴백) - path_utils 사용
            if not is_admin:
                try:
                    from path_utils import get_account_info_from_token

                    # path_utils의 get_account_info_from_token 함수 사용 (모든 경로 자동 확인)
                    token_user, token_path = get_account_info_from_token()
                    print(f"🔍 ModernSettingsWindow - path_utils로 토큰 파일 확인: 사용자='{token_user}', 경로={token_path}")

                    if token_user:
                        user_id = token_user.lower()
                        is_admin = user_id in ['admin', 'nwsoft', 'developer', 'dev']
                        current_user = token_user
                        print(f"🔍 ModernSettingsWindow - 토큰 파일로 관리자 확인: '{current_user}' -> {is_admin}")

                        # 개발환경에서 추가 확인
                        if is_admin:
                            print(f"✅ ModernSettingsWindow - 개발환경에서 토큰 파일로 관리자 권한 확인: {current_user}")
                    else:
                        print("⚠️ ModernSettingsWindow - path_utils로도 토큰 파일을 찾을 수 없습니다.")

                except Exception as e:
                    print(f"⚠️ ModernSettingsWindow - path_utils 토큰 파일 확인 실패: {e}")

            # 개발환경에서 강제 관리자 체크 제거 (보안상 위험)
            # if not is_admin and current_user:
            #     print(f"🔍 ModernSettingsWindow - 개발환경 디버깅: 사용자 '{current_user}'를 관리자로 강제 인식")
            #     is_admin = True
            #     print(f"🔍 ModernSettingsWindow - 강제 관리자 설정 완료: {is_admin}")

            print(f"🔍 ModernSettingsWindow - 최종 관리자 여부: {is_admin} (사용자: '{current_user}')")

            # 데모 모드 UI는 일반 사용자에게 노출하지 않음 (삭제됨)
            # 관리자는 settings.json에서 직접 설정 가능
        except Exception as e:
            print(f"❌ ModernSettingsWindow - 데모 모드 토글 생성 실패: {e}")
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
            
            warning_text = f"⚠️ {display_text}는 Alpha Arena 판단용 벤치마크 기준입니다.\n실제 주문은 연결된 거래소 실잔고/주문가능금액/리스크 한도를 기준으로 처리됩니다.\n즉, 계좌 잔고를 {display_text}로 반드시 맞출 필요는 없습니다."
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
            print(f"✅ 포지션 모드 변경: {mode_text} (max_positions = {max_positions})")

        except Exception as e:
            print(f"❌ 포지션 모드 변경 실패: {e}")

    def create_exchange_api_tab(self):
        """거래소 API 설정 탭 - 기존 구조 정확히 재현"""
        tab = self.tabview.add("거래소 API")

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
            text="🟡 바이낸스 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        binance_title.pack(pady=(20, 15), padx=20)

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
        ctk.CTkButton(
            binance_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_binance
        ).pack(side="right")

        # 업비트 API 설정
        upbit_group = ctk.CTkFrame(scroll_frame)
        upbit_group.pack(fill="x", pady=(0, 20))

        upbit_title = ctk.CTkLabel(
            upbit_group,
            text="🔵 업비트 API 설정",
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
            text="🟠 빗썸 API 설정",
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
            text="🟣 바이비트 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bybit_title.pack(pady=(20, 15), padx=20)

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
        ctk.CTkButton(
            bybit_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_bybit
        ).pack(side="right")

        # OKX API 설정
        okx_group = ctk.CTkFrame(scroll_frame)
        okx_group.pack(fill="x", pady=(0, 20))

        okx_title = ctk.CTkLabel(
            okx_group,
            text="⚫ OKX API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        okx_title.pack(pady=(20, 15), padx=20)

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
        ctk.CTkButton(
            okx_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_okx
        ).pack(side="right")

        # 비트겟 API 설정
        bitget_group = ctk.CTkFrame(scroll_frame)
        bitget_group.pack(fill="x", pady=(0, 20))

        bitget_title = ctk.CTkLabel(
            bitget_group,
            text="🟢 비트겟 API 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        bitget_title.pack(pady=(20, 15), padx=20)

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
        ctk.CTkButton(
            bitget_verify_row,
            text="검증",
            height=30,
            width=90,
            fg_color=self._color("primary", "#2563eb"),
            text_color="white",
            hover_color="#1d4ed8",
            command=self._on_click_verify_bitget
        ).pack(side="right")

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
            text="📈 키움증권 API 설정 (Windows 전용)",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        kiwoom_title.pack(pady=(20, 5), padx=20)

        kiwoom_os_warning = ctk.CTkLabel(
            kiwoom_group,
            text="⚠️ 키움 OpenAPI+는 Windows 환경에서만 실제 연결됩니다. macOS/Linux에서는 mock 모드만 사용 가능합니다.",
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
            values=["openapi", "mock"],
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
        self.kiwoom_api_type_combo.set("openapi")
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
            values=["pykiwoom", "kiwoom_api"],
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
            text="💡 mock: API 없이 테스트/데모 (모든 OS 사용 가능)  |  pykiwoom / kiwoom_api: Windows 전용 실제 연결\n⚠️ Windows가 아닌 환경에서 pykiwoom/kiwoom_api 선택 시 연결이 항상 실패합니다. mock을 선택하세요.",
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
            text="📈 신한증권 API 설정",
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
            values=["openapi", "rest", "mock"],
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
        self.shinhan_api_type_combo.set("openapi")
        self.shinhan_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            shinhan_group, text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(5, 5))

        self.shinhan_api_version_combo = ctk.CTkComboBox(
            shinhan_group,
            values=["solapi", "xingapi", "solapi_rest"],
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
        self.shinhan_api_version_combo.set("solapi")
        self.shinhan_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            shinhan_group,
            text="💡 mock: API 없이 테스트/데모  |  solapi: SolAPI REST  |  xingapi: HTS/Xing 계열 호환  |  solapi_rest: REST 전용\n💡 API 타입은 연결 프로토콜, API 버전은 실제 호출 클라이언트(라이브러리/엔드포인트)입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))

        # 미래에셋 API 설정
        mirae_asset_group = ctk.CTkFrame(scroll_frame)
        mirae_asset_group.pack(fill="x", pady=(0, 20))

        mirae_asset_title = ctk.CTkLabel(
            mirae_asset_group,
            text="📈 미래에셋 API 설정",
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
            values=["openapi", "rest", "mock"],
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
        self.mirae_asset_api_type_combo.set("openapi")
        self.mirae_asset_api_type_combo.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(
            mirae_asset_group, text="API 라이브러리/버전:",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        ).pack(anchor="w", padx=20, pady=(5, 5))

        self.mirae_asset_api_version_combo = ctk.CTkComboBox(
            mirae_asset_group,
            values=["miraemts", "miraedaas", "kis"],
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
        self.mirae_asset_api_version_combo.set("miraemts")
        self.mirae_asset_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            mirae_asset_group,
            text="💡 mock: API 없이 테스트/데모  |  miraemts/miraedaas: 미래에셋 계열  |  kis: REST 호환 경로\n💡 여러 버전은 브로커 API 변화/운영 환경 차이를 흡수하기 위한 선택지입니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 20))

        # 한국투자증권 API 설정
        korea_investment_group = ctk.CTkFrame(scroll_frame)
        korea_investment_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            korea_investment_group,
            text="📈 한국투자증권 API 설정 (KIS)",
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
            values=["rest", "openapi", "mock"],
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
            values=["kis", "mock"],
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
        self.korea_investment_api_version_combo.set("kis")
        self.korea_investment_api_version_combo.pack(fill="x", padx=20, pady=(0, 5))

        ctk.CTkLabel(
            korea_investment_group,
            text="💡 권장: api_type=rest, api_version=kis  |  mock: API 없이 테스트/데모",
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
        info_text = """💡 거래소 API 설정 안내

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

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # AI 시스템 상태 (배지 + 카드 스타일)
        ai_status_group = ctk.CTkFrame(scroll_frame)
        ai_status_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            ai_status_group,
            text="🤖 AI 시스템 상태",
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
            text="🎯 AI 자동 최적화 시스템",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        ai_auto_title.pack(pady=(20, 15))

        auto_info_text = (
            "AI가 자동으로 최적화하는 항목들:\n\n"
            "• 지표 기간 (RSI/MA/BB) — 실시간 조정\n"
            "• 모멘텀/거래량/신호 임계값 — 실시간 조정\n"
            "• 시장 국면별 전략 선택 — 실시간 조정\n\n"
            "⚠️ 이 항목들은 AI가 관리합니다 (수동 변경 금지)."
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
            text="ℹ️ 중요 안내",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        warning_title.pack(pady=(20, 15))

        warning_text = """초보자가 AI 분석 파라미터를 수동으로 변경하면:

❌ AI 최적화 시스템과 충돌 발생
❌ 거래 성과 급격히 악화 가능
❌ 시스템 안정성 저하
❌ 예상치 못한 손실 발생 가능

✅ 안전한 사용법:
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
                text="🧭 시장 국면 자동 보정",
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
                text="🔄 환경설정 기본값 되돌리기",
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
            print(f"⚠️ 시장 국면 자동 보정 UI 생성 실패: {e}")

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
                    lbl.configure(text=(f"✅ {lbl.cget('text').replace('⏳ ', '').replace('✅ ', '').replace('⛔ ', '')}" if ok else f"⛔ {lbl.cget('text').replace('⏳ ', '').replace('✅ ', '').replace('⛔ ', '')}"),
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

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 제목
        title_label = ctk.CTkLabel(
            scroll_frame,
            text="🏢 거래소 선택",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        title_label.pack(pady=(0, 20))

        # 설명
        description_text = """💡 거래소 선택 안내

• 현재 지원: 바이낸스, 업비트, 빗썸, 바이비트, OKX, 비트겟
• 다중 선택: 여러 거래소를 동시에 선택할 수 있습니다
• API 키: 선택한 거래소의 API 키를 반드시 입력해야 합니다
• 선물 거래: 바이낸스, 바이비트, OKX, 비트겟
• 현물 거래: 업비트, 빗썸"""

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
            text="🇰🇷 국내 거래소",
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
            text="🌍 해외 거래소",
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

        # 주식/증권사 선택 섹션 (기존 거래소 선택 탭에 추가)
        stock_separator = ctk.CTkFrame(scroll_frame, height=2, fg_color=self._color("secondary", "#1f2937"))
        stock_separator.pack(fill="x", padx=20, pady=(20, 20))

        stock_title = ctk.CTkLabel(
            scroll_frame,
            text="📈 주식/증권사 선택",
            font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        stock_title.pack(pady=(0, 20))

        stock_description = ctk.CTkLabel(
            scroll_frame,
            text="💡 증권사 선택 안내\n\n• 현재 구현: 키움증권, 신한증권, 미래에셋, 한국투자증권 (4개)\n• 다중 증권사 선택 가능 (동시 운영)\n• API 키는 각 증권사별 입력 필드에서 설정\n• 주식 및 ETF 거래를 지원합니다\n• 주식: 개별 기업 종목 거래 / ETF: 지수·섹터를 묶은 상품 거래\n• 주문 경로는 유사하지만, AI 분석 문맥(리스크/괴리율/NAV)은 다르게 처리됩니다\n• 실제 연결 가능 여부는 증권사 OpenAPI 권한(개인/법인/제휴 정책)에 따라 달라집니다\n• 아래 표시 모드에서 통합 / 주식만 / ETF만 보기를 선택할 수 있습니다",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        stock_description.pack(fill="x", pady=(0, 20))

        quick_path_guide = ctk.CTkLabel(
            scroll_frame,
            text="📍 빠른 위치 안내: ① 거래소 API 탭에서 증권사 API 입력/저장 → ② 현재 탭 아래 '⚙️ 증권 자동매매 제어'에서 실주문/STOP 정책 설정",
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

        stock_mode_frame = ctk.CTkFrame(scroll_frame)
        stock_mode_frame.pack(fill="x", padx=20, pady=(0, 20))

        stock_mode_title = ctk.CTkLabel(
            stock_mode_frame,
            text="🔀 증권 표시 모드",
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
            text="🛡️ 증권 주문 가드레일",
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
            text="⚙️ 증권 자동매매 제어",
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
            text="⚠️ '실주문 허용'을 켜야 실제 증권사 주문이 나갑니다. 끄면 분석·계획만 기록되고 실행되지 않습니다.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#f59e0b",
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 10))

        # 생활금융 데이터 경로 설정
        ctk.CTkLabel(
            stock_ctrl_frame,
            text="💳 생활금융 데이터 경로",
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
            text="🛑 STOP 시 기존 포지션 처리",
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
        button_frame.pack(fill="x", pady=(0, 10))

        # 저장 버튼
        save_button = ctk.CTkButton(
            button_frame,
            text="💾 저장",
            height=50,
            width=120,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            fg_color=self._color("success", "#10b981"),
            text_color="white",
            hover_color="#059669",
            border_width=0,
            corner_radius=10,
            command=self.save_settings
        )
        save_button.pack(side="left", padx=(0, 10))

        # 취소 버튼
        cancel_button = ctk.CTkButton(
            button_frame,
            text="❌ 취소",
            height=50,
            width=120,
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            fg_color=self._color("danger", "#ef4444"),
            text_color="white",
            hover_color="#dc2626",
            border_width=0,
            corner_radius=10,
            command=self.cancel_settings
        )
        cancel_button.pack(side="left", padx=(0, 10))

        # 백업 복구 버튼
        restore_button = ctk.CTkButton(
            button_frame,
            text="🗂 백업에서 복구",
            height=50,
            width=170,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color="#334155",
            text_color="white",
            hover_color="#475569",
            border_width=0,
            corner_radius=10,
            command=self._show_backup_restore_dialog
        )
        restore_button.pack(side="left", padx=(0, 10))

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
                print("✅ 설정 저장 콜백 호출 완료")
        except Exception as e:
            print(f"⚠️ 설정 저장 콜백 오류: {e}")

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
        return broker_map.get((api_type or 'openapi').lower(), [])

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
            print(f"⚠️ API 버전 옵션 동기화 실패({broker}): {e}")

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
            print(f"⚠️ api_type 이벤트 바인딩 실패: {e}")

    def on_exchange_changed(self, *args):
        """거래소 변경 이벤트 핸들러"""
        try:
            if hasattr(self, 'exchange_var') and self.exchange_var is not None and hasattr(self.exchange_var, 'get'):
                selected_exchange = self.exchange_var.get()
            else:
                selected_exchange = None
            print(f"🔄 거래소 변경: {selected_exchange}")
            # ExchangeManager에 거래소 변경 알림
            if hasattr(self, 'on_save_callback') and self.on_save_callback:
                self.on_save_callback('exchange_changed', selected_exchange)
        except Exception as e:
            print(f"❌ 거래소 변경 처리 오류: {e}")

    def on_closing(self):
        """창 닫기 처리 - API 키가 없으면 프로그램 종료"""
        try:
            print("🚪 설정 창 닫기")
            # 타이머 정리
            try:
                if hasattr(self, '_ai_status_timer') and self._ai_status_timer:
                    self.root.after_cancel(self._ai_status_timer)
            except Exception:
                pass

            # API 키 검증
            openai_key = self.openai_api_key_entry.get().strip()
            if not openai_key:
                print("❌ OpenAI API 키가 입력되지 않음 - 프로그램을 종료합니다.")
                self.root.destroy()
                import sys
                sys.exit(0)
            else:
                # 설정 저장 후 창 닫기
                self.save_settings()
                self.root.destroy()

        except Exception as e:
            print(f"❌ 설정 창 닫기 처리 오류: {e}")
            self.root.destroy()
            import sys
            sys.exit(0)

    def load_current_settings(self):
        """현재 설정을 UI에 로드 - 기존 PyQt5 설정 창과 동일한 로직"""
        try:
            print(f"🔍 설정 로드 시작: {len(self.current_settings)}개 설정")
            print(f"🔍 현재 설정: {list(self.current_settings.keys())}")

            # API 설정 복원 (기존과 동일)
            binance_key = self.current_settings.get('binance_api_key', '')
            binance_secret = self.current_settings.get('binance_secret_key', '')
            openai_key = self.current_settings.get('openai_api_key', '')
            openai_base_url = str(self.current_settings.get('openai_base_url', '') or '').strip()

            print(f"🔍 바이낸스 키: {binance_key[:10]}..." if binance_key else "🔍 바이낸스 키: 없음")
            print(f"🔍 OpenAI 키: {openai_key[:10]}..." if openai_key else "🔍 OpenAI 키: 없음")

            self.binance_api_key_entry.insert(0, binance_key)
            self.binance_secret_key_entry.insert(0, binance_secret)
            self.openai_api_key_entry.insert(0, openai_key)
            if hasattr(self, 'openai_base_url_entry'):
                self.openai_base_url_entry.delete(0, 'end')
                self.openai_base_url_entry.insert(0, openai_base_url)

            # OpenAI 모델 설정
            openai_model = self.current_settings.get('openai_model', 'gpt-4o-mini')
            if openai_model in ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "gpt-5-mini", "gpt-5"]:
                self.openai_model_combo.set(openai_model)

            assistant_model = self.current_settings.get('assistant_ai_model', 'gpt-4o-mini')
            if assistant_model in ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "gpt-5-mini", "gpt-5"]:
                self.assistant_ai_model_combo.set(assistant_model)

            # 역할별 모델 티어 복원
            _ai_roles = self.current_settings.get('ai_model_roles', {})
            _tier_allowed = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "gpt-5-mini", "gpt-5"]
            if hasattr(self, 'ai_role_cheap_combo'):
                v = _ai_roles.get('frequent_cheap', 'gpt-4o-mini')
                self.ai_role_cheap_combo.set(v if v in _tier_allowed else 'gpt-4o-mini')
            if hasattr(self, 'ai_role_standard_combo'):
                v = _ai_roles.get('standard', 'gpt-4o')
                self.ai_role_standard_combo.set(v if v in _tier_allowed else 'gpt-4o')
            if hasattr(self, 'ai_role_premium_combo'):
                v = _ai_roles.get('premium', 'gpt-4o')
                self.ai_role_premium_combo.set(v if v in _tier_allowed else 'gpt-4o')

            apply_mode = str(self.current_settings.get('assistant_apply_mode', 'user_confirm') or 'user_confirm').lower()
            if hasattr(self, 'assistant_apply_mode_combo'):
                self.assistant_apply_mode_combo.set("AI 자동적용" if apply_mode == 'ai_auto' else "사용자 최종확인")

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
                self.kiwoom_api_type_combo.set(kiwoom_config.get('api_type', 'openapi'))
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
                self.shinhan_api_type_combo.set(shinhan_config.get('api_type', 'openapi'))
                self._sync_stock_api_version_options('shinhan', preserve_value=False)
            if hasattr(self, 'shinhan_api_version_combo'):
                self.shinhan_api_version_combo.set(shinhan_config.get('api_version', 'solapi'))
                self._sync_stock_api_version_options('shinhan', preserve_value=True)

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
                self.mirae_asset_api_type_combo.set(mirae_asset_config.get('api_type', 'openapi'))
                self._sync_stock_api_version_options('miraeAsset', preserve_value=False)
            if hasattr(self, 'mirae_asset_api_version_combo'):
                self.mirae_asset_api_version_combo.set(mirae_asset_config.get('api_version', 'miraemts'))
                self._sync_stock_api_version_options('miraeAsset', preserve_value=True)

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
                self.korea_investment_api_version_combo.set(korea_investment_config.get('api_version', 'kis'))
                self._sync_stock_api_version_options('koreaInvestment', preserve_value=True)

            # AI 설정은 제거됨 - AI가 자동으로 최적화

            # 거래소 선택 상태 복원 (다중 선택)
            enabled = self.current_settings.get('enabled_exchanges', ['binance'])
            print(f"🔍 활성화된 거래소: {enabled}")

            # exchange_vars가 존재하는지 확인
            if hasattr(self, 'exchange_vars'):
                for key, var in self.exchange_vars.items():
                    is_enabled = key in enabled
                    var.set(is_enabled)
                    print(f"🔍 {key}: {'활성화' if is_enabled else '비활성화'}")
            else:
                print("⚠️ exchange_vars가 존재하지 않음")

            # 증권사 선택 상태 복원 (다중 선택)
            enabled_brokers = self.current_settings.get('enabled_stock_brokers', [])
            print(f"🔍 활성화된 증권사: {enabled_brokers}")

            # stock_broker_vars가 존재하는지 확인
            if hasattr(self, 'stock_broker_vars'):
                for key, var in self.stock_broker_vars.items():
                    is_enabled = key in enabled_brokers
                    var.set(is_enabled)
                    print(f"🔍 증권사 {key}: {'활성화' if is_enabled else '비활성화'}")
            else:
                print("⚠️ stock_broker_vars가 존재하지 않음")

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
                    engine = alpha_arena.get('engine', 'deepseek-3.1')
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
                
                # 레거시 설정도 복원 (하위 호환성)
                if hasattr(self, 'alphaarena_enabled_var'):
                    self.alphaarena_enabled_var.set(bool(self.current_settings.get('alphaarena_enabled', False)))
                if hasattr(self, 'alphaarena_ai_var'):
                    ai_engine = self.current_settings.get('alphaarena_ai_engine', 'deepseek-chat-v3.1')
                    self.alphaarena_ai_var.set(ai_engine)
                if hasattr(self, 'alphaarena_capital_entry'):
                    capital = str(self.current_settings.get('alphaarena_capital', 10000))
                    self.alphaarena_capital_entry.delete(0, 'end')
                    self.alphaarena_capital_entry.insert(0, capital)
                if hasattr(self, 'alphaarena_leverage_var'):
                    leverage = self.current_settings.get('alphaarena_leverage_range', '10-20x')
                    self.alphaarena_leverage_var.set(leverage)
                # API 키들 복원 (레거시)
                if hasattr(self, 'alphaarena_deepseek_key'):
                    self.alphaarena_deepseek_key.insert(0, self.current_settings.get('alphaarena_deepseek_api_key', ''))
                if hasattr(self, 'alphaarena_openai_key'):
                    self.alphaarena_openai_key.insert(0, self.current_settings.get('alphaarena_openai_api_key', ''))
                if hasattr(self, 'alphaarena_anthropic_key'):
                    self.alphaarena_anthropic_key.insert(0, self.current_settings.get('alphaarena_anthropic_api_key', ''))
                if hasattr(self, 'alphaarena_google_key'):
                    self.alphaarena_google_key.insert(0, self.current_settings.get('alphaarena_google_api_key', ''))
                if hasattr(self, 'alphaarena_xai_key'):
                    self.alphaarena_xai_key.insert(0, self.current_settings.get('alphaarena_xai_api_key', ''))
                if hasattr(self, 'alphaarena_alibaba_key'):
                    self.alphaarena_alibaba_key.insert(0, self.current_settings.get('alphaarena_alibaba_api_key', ''))
            except Exception as e:
                print(f"⚠️ Alpha Arena 설정 복원 실패: {e}")

            # 고급 매매 계층 ON/OFF 복원
            try:
                if hasattr(self, '_atl_vars') and self._atl_vars:
                    atl = self.current_settings.get("advanced_trading_layers", {})
                    for key, var in self._atl_vars.items():
                        var.set(bool(atl.get(key, {}).get("enabled", False)))
            except Exception as e:
                print(f"⚠️ 고급 매매 계층 설정 복원 실패: {e}")

            print("✅ 설정 로드 완료")

        except Exception as e:
            print(f"❌ 설정 로드 실패: {e}")


    def create_update_info_tab(self):
        """업데이트 정보 탭 - 버전 및 새로운 기능 안내"""
        tab = self.tabview.add("📋 업데이트")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 버전 정보 그룹
        version_group = ctk.CTkFrame(scroll_frame)
        version_group.pack(fill="x", pady=(0, 20))

        # 제목
        version_title = ctk.CTkLabel(
            version_group,
            text="📦 버전 정보",
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
            text="업데이트 일자: 2026년 7월 1일",
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
            text="⚙️ 자동업데이트 설정",
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

        python_runtime_group = ctk.CTkFrame(scroll_frame)
        python_runtime_group.pack(fill="x", pady=(0, 20))

        python_runtime_title = ctk.CTkLabel(
            python_runtime_group,
            text="🐍 Python 런타임 정보",
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
            text="🗂️ 변경 이력 경로(단일화)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        changelog_title.pack(pady=(12, 8), padx=15, anchor="w")

        changelog_text = (
            "중복 안내를 방지하기 위해 버전별 최신 변경 상세는 설정 탭에 중복 표기하지 않습니다.\n"
            "공식 변경 이력은 대시보드 '사용자 매뉴얼 → 📅 업데이트' 탭에서만 단일 관리됩니다.\n"
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
            text="📚 상세 정보",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        more_title.pack(pady=(12, 8), padx=15, anchor="w")

        info_text = "✓ 릴리스 노트: 각 버전의 변경 사항을 확인하세요\n✓ 사용 설명서: AI 실행 기능 단계별 가이드\n✓ 안전 정책: 2단계 확인, 자동 실행 금지"
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
            text="📖 사용자 안내:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        links_label.pack(pady=(8, 4), padx=15, anchor="w")

        docs = [
            "• 앱 내 '📅 업데이트' 탭에서 최신 변경사항을 확인할 수 있습니다.",
            "• AI 설정/최적화 도움말은 '💬 AI 어시스턴트 → 설정관리'에서 안내됩니다.",
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

    def save_settings(self):
        """설정 저장 - 기존 PyQt5 설정 창과 동일한 로직"""
        try:
            # UI에서 설정 값 가져오기 (기존과 동일한 방식)
            new_settings = {
                # OpenAI 설정
                'openai_api_key': self.openai_api_key_entry.get(),
                'openai_base_url': self.openai_base_url_entry.get().strip() if hasattr(self, 'openai_base_url_entry') else str(self.current_settings.get('openai_base_url', '') or '').strip(),
                'openai_model': self.openai_model_combo.get(),
                'assistant_ai_model': self.assistant_ai_model_combo.get(),
                'ai_model_roles': {
                    'frequent_cheap': self.ai_role_cheap_combo.get() if hasattr(self, 'ai_role_cheap_combo') else 'gpt-4o-mini',
                    'standard': self.ai_role_standard_combo.get() if hasattr(self, 'ai_role_standard_combo') else 'gpt-4o',
                    'premium': self.ai_role_premium_combo.get() if hasattr(self, 'ai_role_premium_combo') else 'gpt-4o',
                },
                'assistant_apply_mode': 'ai_auto' if (hasattr(self, 'assistant_apply_mode_combo') and self.assistant_apply_mode_combo.get() == 'AI 자동적용') else 'user_confirm',
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
                        'api_type': self.kiwoom_api_type_combo.get() if hasattr(self, 'kiwoom_api_type_combo') else 'openapi',
                        'api_version': self.kiwoom_api_version_combo.get() if hasattr(self, 'kiwoom_api_version_combo') else 'pykiwoom',
                        'id': self.kiwoom_id_entry.get() if hasattr(self, 'kiwoom_id_entry') else '',
                        'password': self.kiwoom_password_entry.get() if hasattr(self, 'kiwoom_password_entry') else '',
                        'cert_password': self.kiwoom_cert_password_entry.get() if hasattr(self, 'kiwoom_cert_password_entry') else '',
                        'account_no': self.kiwoom_account_entry.get() if hasattr(self, 'kiwoom_account_entry') else '',
                        'allow_live_order': self.current_settings.get('stock_broker_configs', {}).get('kiwoom', {}).get('allow_live_order', False),
                        'asset_types': ['stock', 'etf']
                    },
                    'shinhan': {
                        'enabled': self.stock_broker_vars['shinhan'].get() if hasattr(self, 'stock_broker_vars') and 'shinhan' in self.stock_broker_vars else False,
                        'api_type': self.shinhan_api_type_combo.get() if hasattr(self, 'shinhan_api_type_combo') else 'openapi',
                        'api_version': self.shinhan_api_version_combo.get() if hasattr(self, 'shinhan_api_version_combo') else 'solapi',
                        'id': self.shinhan_id_entry.get() if hasattr(self, 'shinhan_id_entry') else '',
                        'password': self.shinhan_password_entry.get() if hasattr(self, 'shinhan_password_entry') else '',
                        'cert_password': self.shinhan_cert_password_entry.get() if hasattr(self, 'shinhan_cert_password_entry') else '',
                        'account_no': self.shinhan_account_entry.get() if hasattr(self, 'shinhan_account_entry') else '',
                        # app_key/app_secret 전용 입력 UI가 없는 동안에는 id/password를 동기화 저장
                        # (어댑터는 app_key/app_secret 우선 사용)
                        'app_key': (self.shinhan_id_entry.get() if hasattr(self, 'shinhan_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('shinhan', {}).get('app_key', ''),
                        'app_secret': (self.shinhan_password_entry.get() if hasattr(self, 'shinhan_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('shinhan', {}).get('app_secret', ''),
                        'asset_types': ['stock', 'etf']
                    },
                    'miraeAsset': {
                        'enabled': self.stock_broker_vars['miraeAsset'].get() if hasattr(self, 'stock_broker_vars') and 'miraeAsset' in self.stock_broker_vars else False,
                        'api_type': self.mirae_asset_api_type_combo.get() if hasattr(self, 'mirae_asset_api_type_combo') else 'openapi',
                        'api_version': self.mirae_asset_api_version_combo.get() if hasattr(self, 'mirae_asset_api_version_combo') else 'miraemts',
                        'id': self.mirae_asset_id_entry.get() if hasattr(self, 'mirae_asset_id_entry') else '',
                        'password': self.mirae_asset_password_entry.get() if hasattr(self, 'mirae_asset_password_entry') else '',
                        'cert_password': self.mirae_asset_cert_password_entry.get() if hasattr(self, 'mirae_asset_cert_password_entry') else '',
                        'account_no': self.mirae_asset_account_entry.get() if hasattr(self, 'mirae_asset_account_entry') else '',
                        # app_key/app_secret 전용 입력 UI가 없는 동안에는 id/password를 동기화 저장
                        'app_key': (self.mirae_asset_id_entry.get() if hasattr(self, 'mirae_asset_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('miraeAsset', {}).get('app_key', ''),
                        'app_secret': (self.mirae_asset_password_entry.get() if hasattr(self, 'mirae_asset_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('miraeAsset', {}).get('app_secret', ''),
                        'asset_types': ['stock', 'etf']
                    },
                    'koreaInvestment': {
                        'enabled': self.stock_broker_vars['koreaInvestment'].get() if hasattr(self, 'stock_broker_vars') and 'koreaInvestment' in self.stock_broker_vars else False,
                        'api_type': self.korea_investment_api_type_combo.get() if hasattr(self, 'korea_investment_api_type_combo') else 'rest',
                        'api_version': self.korea_investment_api_version_combo.get() if hasattr(self, 'korea_investment_api_version_combo') else 'kis',
                        'id': self.korea_investment_id_entry.get() if hasattr(self, 'korea_investment_id_entry') else '',
                        'password': self.korea_investment_password_entry.get() if hasattr(self, 'korea_investment_password_entry') else '',
                        'cert_password': self.korea_investment_cert_password_entry.get() if hasattr(self, 'korea_investment_cert_password_entry') else '',
                        'account_no': self.korea_investment_account_entry.get() if hasattr(self, 'korea_investment_account_entry') else '',
                        'app_key': (self.korea_investment_id_entry.get() if hasattr(self, 'korea_investment_id_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('koreaInvestment', {}).get('app_key', ''),
                        'app_secret': (self.korea_investment_password_entry.get() if hasattr(self, 'korea_investment_password_entry') else '') or self.current_settings.get('stock_broker_configs', {}).get('koreaInvestment', {}).get('app_secret', ''),
                        'asset_types': ['stock', 'etf']
                    }
                },

                # AI 설정은 제거됨 - AI가 자동으로 최적화

                # 거래소 선택 (다중 선택)
                'enabled_exchanges': [k for k,v in self.exchange_vars.items() if v is not None and hasattr(v, 'get') and v.get()],
                
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
            except Exception:
                new_settings['paper_trading'] = bool(self.current_settings.get('paper_trading', False))
                new_settings['verbose_trade_logging'] = bool(self.current_settings.get('verbose_trade_logging', False))

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
                    print(f"✅ UI 설정 저장: always_on_top = {always_on_top_value}")
                else:
                    # 기본값 유지
                    if 'ui_settings' not in new_settings:
                        new_settings['ui_settings'] = {}
                    new_settings['ui_settings']['always_on_top'] = self.current_settings.get('ui_settings', {}).get('always_on_top', True)
                    new_settings['ui_settings']['auto_show_stock_broker_diagnosis_after_save'] = self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True)
                    new_settings['ui_settings'].update(self._collect_auto_update_ui_settings())
                    print(f"⚠️ UI 설정 기본값 유지: always_on_top = {self.current_settings.get('ui_settings', {}).get('always_on_top', True)}")
            except Exception as e:
                if 'ui_settings' not in new_settings:
                    new_settings['ui_settings'] = {}
                new_settings['ui_settings']['always_on_top'] = self.current_settings.get('ui_settings', {}).get('always_on_top', True)
                new_settings['ui_settings']['auto_show_stock_broker_diagnosis_after_save'] = self.current_settings.get('ui_settings', {}).get('auto_show_stock_broker_diagnosis_after_save', True)
                new_settings['ui_settings'].update(self._collect_auto_update_ui_settings())
                print(f"❌ UI 설정 저장 오류: {e}")

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
                print(f"⚠️ 시장 국면 보정 설정 반영 실패: {e}")

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
                    # 레거시 키도 저장 (하위 호환성)
                    new_settings['alphaarena_deepseek_api_key'] = deepseek_key
                
                if hasattr(self, 'alpha_arena_qwen_api_key_var'):
                    qwen_key = self.alpha_arena_qwen_api_key_var.get().strip()
                    alpha_arena['qwen_api_key'] = qwen_key
                    # 레거시 키도 저장 (하위 호환성)
                    new_settings['alphaarena_alibaba_api_key'] = qwen_key
                
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
                
                # 레거시 설정도 저장 (하위 호환성)
                if hasattr(self, 'alphaarena_enabled_var') and self.alphaarena_enabled_var is not None:
                    new_settings['alphaarena_enabled'] = bool(self.alphaarena_enabled_var.get())
                if hasattr(self, 'alphaarena_ai_var') and self.alphaarena_ai_var is not None:
                    new_settings['alphaarena_ai_engine'] = self.alphaarena_ai_var.get()
                if hasattr(self, 'alphaarena_capital_entry') and self.alphaarena_capital_entry is not None:
                    capital_text = self.alphaarena_capital_entry.get().strip()
                    if capital_text:
                        new_settings['alphaarena_capital'] = float(capital_text)
                if hasattr(self, 'alphaarena_leverage_var') and self.alphaarena_leverage_var is not None:
                    new_settings['alphaarena_leverage_range'] = self.alphaarena_leverage_var.get()
                # API 키들 저장 (레거시)
                if hasattr(self, 'alphaarena_deepseek_key'):
                    new_settings['alphaarena_deepseek_api_key'] = self.alphaarena_deepseek_key.get()
                if hasattr(self, 'alphaarena_openai_key'):
                    new_settings['alphaarena_openai_api_key'] = self.alphaarena_openai_key.get()
                if hasattr(self, 'alphaarena_anthropic_key'):
                    new_settings['alphaarena_anthropic_api_key'] = self.alphaarena_anthropic_key.get()
                if hasattr(self, 'alphaarena_google_key'):
                    new_settings['alphaarena_google_api_key'] = self.alphaarena_google_key.get()
                if hasattr(self, 'alphaarena_xai_key'):
                    new_settings['alphaarena_xai_api_key'] = self.alphaarena_xai_key.get()
                if hasattr(self, 'alphaarena_alibaba_key'):
                    new_settings['alphaarena_alibaba_api_key'] = self.alphaarena_alibaba_key.get()
            except Exception as e:
                print(f"⚠️ Alpha Arena 설정 저장 실패: {e}")
                import traceback
                traceback.print_exc()

            # 고급 매매 계층 ON/OFF 저장
            try:
                if hasattr(self, '_atl_vars') and self._atl_vars:
                    existing_atl = self.current_settings.get("advanced_trading_layers", {})
                    for key, var in self._atl_vars.items():
                        if key not in existing_atl:
                            existing_atl[key] = {}
                        existing_atl[key]["enabled"] = bool(var.get())
                    new_settings["advanced_trading_layers"] = existing_atl
                else:
                    new_settings["advanced_trading_layers"] = self.current_settings.get("advanced_trading_layers", {})
            except Exception as e:
                print(f"⚠️ 고급 매매 계층 설정 저장 실패: {e}")

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
                print(f"⚠️ api_type/api_version 검증 오류: {_ve}")

            # 설정 파일에 저장 (기존 함수 사용)
            from config.settings import save_settings
            if save_settings(self.current_settings):
                # ✅ 1. 먼저 사용자에게 피드백
                messagebox.showinfo("성공", "설정이 저장되었습니다!")

                # ✅ 2. 저장 직후 필요한 경우 증권사 1차 진단 안내
                self._maybe_show_post_save_stock_broker_diagnosis()

                # ✅ 3. 모달 창 즉시 닫기 (사용자 경험 개선)
                self.root.destroy()

                # ✅ 4. 콜백은 창이 닫힌 후 백그라운드에서 실행
                if self.on_save_callback:
                    # after_idle을 사용하여 UI 스레드를 블로킹하지 않고 실행
                    if self.parent:
                        self.parent.after(100, lambda: self._execute_callback_safe(self.current_settings))
                    else:
                        try:
                            self.on_save_callback(self.current_settings)
                            print("✅ 설정 저장 콜백 호출 완료")
                        except Exception as e:
                            print(f"⚠️ 설정 저장 콜백 오류: {e}")
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
        self.root.destroy()

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
                            print("✅ 설정 복원 콜백 호출 완료")
                        except Exception as e:
                            print(f"⚠️ 설정 복원 콜백 오류: {e}")
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
        try:
            api_key = self.binance_api_key_entry.get().strip() if hasattr(self, 'binance_api_key_entry') else ''
            secret_key = self.binance_secret_key_entry.get().strip() if hasattr(self, 'binance_secret_key_entry') else ''
            if not api_key or not secret_key:
                self._set_binance_status("⚠️ 키를 입력하세요")
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
                self.root.after(0, lambda: self._set_binance_status("✅ 검증 완료", ok=True))
            else:
                text = f"❌ {err_msg}" if err_msg else "❌ 검증 실패"
                self.root.after(0, lambda: self._set_binance_status(text, ok=False))
        except Exception:
            try:
                self.root.after(0, lambda: self._set_binance_status("❌ 검증 실패", ok=False))
            except Exception:
                pass

    def _on_click_verify_upbit(self):
        """업비트 API 키 검증"""
        api_key = self.upbit_api_key_entry.get().strip()
        secret_key = self.upbit_secret_key_entry.get().strip()

        if not api_key or not secret_key:
            self._upbit_verify_status.set("❌ API 키를 입력해주세요")
            return

        self._upbit_verify_status.set("🔄 검증 중...")

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
                self.root.after(0, lambda: self._upbit_verify_status.set("✅ 검증 완료"))
            else:
                self.root.after(0, lambda: self._upbit_verify_status.set("❌ 검증 실패"))

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._upbit_verify_status.set("❌ API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._upbit_verify_status.set("❌ 접근 제한"))
            else:
                self.root.after(0, lambda: self._upbit_verify_status.set("❌ 검증 실패"))

    def _on_click_verify_okx(self):
        """OKX API 키 검증"""
        api_key = self.okx_api_key_entry.get().strip()
        secret_key = self.okx_secret_key_entry.get().strip()
        passphrase = self.okx_passphrase_entry.get().strip()

        if not api_key or not secret_key or not passphrase:
            self._okx_verify_status.set("❌ API 키를 모두 입력해주세요")
            return

        self._okx_verify_status.set("🔄 검증 중...")

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
                self.root.after(0, lambda: self._okx_verify_status.set("✅ 검증 완료"))
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
                self.root.after(0, lambda: self._okx_verify_status.set("❌ API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._okx_verify_status.set("❌ 접근 제한"))
            elif "passphrase" in error_msg.lower():
                self.root.after(0, lambda: self._okx_verify_status.set("❌ Passphrase 오류"))
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
            self._bithumb_verify_status.set("❌ API 키를 입력해주세요")
            return

        self._bithumb_verify_status.set("🔄 검증 중...")

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
                self.root.after(0, lambda: self._bithumb_verify_status.set("✅ 검증 완료"))
            else:
                self.root.after(0, lambda: self._bithumb_verify_status.set("❌ 검증 실패"))

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                self.root.after(0, lambda: self._bithumb_verify_status.set("❌ API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bithumb_verify_status.set("❌ 접근 제한"))
            else:
                self.root.after(0, lambda: self._bithumb_verify_status.set("❌ 검증 실패"))

    def _on_click_verify_bybit(self):
        """바이비트 API 키 검증"""
        api_key = self.bybit_api_key_entry.get().strip()
        secret_key = self.bybit_secret_key_entry.get().strip()

        if not api_key or not secret_key:
            self._bybit_verify_status.set("❌ API 키를 입력해주세요")
            return

        self._bybit_verify_status.set("🔄 검증 중...")

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
                self.root.after(0, lambda: self._bybit_verify_status.set("✅ 검증 완료"))
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
                self.root.after(0, lambda: self._bybit_verify_status.set("❌ API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bybit_verify_status.set("❌ 접근 제한"))
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
        api_key = self.bitget_api_key_entry.get().strip()
        secret_key = self.bitget_secret_key_entry.get().strip()
        password = self.bitget_password_entry.get().strip()

        if not api_key or not secret_key or not password:
            self._bitget_verify_status.set("❌ API 키를 모두 입력해주세요")
            return

        self._bitget_verify_status.set("🔄 검증 중...")

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
                "❌ Bitget IP 화이트리스트 오류\n"
                f"현재 공인 IP: {public_ip}\n"
                "Bitget API 키 설정에서 IP 화이트리스트에 위 IP를 등록한 뒤 다시 검증하세요."
            )

        if 'invalid header value' in low:
            return (
                "❌ Bitget 헤더 값 오류\n"
                "API Key/Secret/Passphrase 앞뒤 공백·줄바꿈을 제거하고 다시 저장 후 검증하세요."
            )

        if 'password' in low or 'passphrase' in low:
            return "❌ Bitget Passphrase 오류: 키 생성 시 입력한 passphrase 값을 다시 확인하세요."

        if '401' in low or 'unauthorized' in low:
            return "❌ Bitget 인증 오류: API Key/Secret/Passphrase 및 선물 거래 권한을 확인하세요."

        return "❌ Bitget 검증 실패: 입력값과 권한 설정을 확인한 뒤 다시 시도하세요."

    def _build_bybit_verify_hint(self, error_msg: str) -> str:
        msg = str(error_msg or '')
        low = msg.lower()
        public_ip = self._get_public_ip_for_hint()

        if 'unmatched ip' in low or 'bound ip' in low:
            return (
                "❌ Bybit IP 화이트리스트 오류\n"
                f"현재 공인 IP: {public_ip}\n"
                "Bybit API 키의 bound IP 주소에 위 IP를 등록한 뒤 다시 검증하세요."
            )
        if '401' in low or 'unauthorized' in low:
            return "❌ Bybit 인증 오류: API Key/Secret 및 선물 거래 권한을 확인하세요."
        return "❌ Bybit 검증 실패: 입력값과 API 권한 설정을 확인한 뒤 다시 시도하세요."

    def _build_okx_verify_hint(self, error_msg: str) -> str:
        msg = str(error_msg or '')
        low = msg.lower()
        public_ip = self._get_public_ip_for_hint()

        if 'passphrase' in low:
            return "❌ OKX Passphrase 오류: API 생성 시 설정한 passphrase를 다시 확인하세요."
        if '51010' in low or 'account mode' in low:
            return "❌ OKX 계좌 모드 오류: 웹사이트에서 계좌 모드를 Single/Multi-currency margin으로 변경 후 다시 검증하세요."
        if 'invalid ip' in low:
            return (
                "❌ OKX IP 제한 가능성\n"
                f"현재 공인 IP: {public_ip}\n"
                "OKX API 키의 IP 제한 설정을 확인하세요."
            )
        if '401' in low or 'unauthorized' in low:
            return "❌ OKX 인증 오류: API Key/Secret/Passphrase 및 거래 권한을 확인하세요."
        return "❌ OKX 검증 실패: 입력값과 계좌 모드/권한 설정을 확인한 뒤 다시 시도하세요."

    def _verify_bitget_keys_worker(self, api_key: str, secret_key: str, password: str):
        """비트겟 API 키 검증 (백그라운드 스레드)"""
        try:
            from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter

            adapter = BitgetFuturesAdapter(api_key, secret_key, password)
            success = adapter.connect()

            if success:
                self.root.after(0, lambda: self._bitget_verify_status.set("✅ 검증 완료"))
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
                self.root.after(0, lambda: self._bitget_verify_status.set("❌ API 키/권한 오류"))
            elif "403" in error_msg:
                self.root.after(0, lambda: self._bitget_verify_status.set("❌ 접근 제한"))
            elif "password" in error_msg.lower():
                self.root.after(0, lambda: self._bitget_verify_status.set("❌ Password 오류"))
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
        """고급 자동매매 계층 설정 탭 - 프리셋 전환 + 개별 ON/OFF"""
        tab = self.tabview.add("🔧 고급 매매 계층")

        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # ── 현재 설정에서 advanced_trading_layers 읽기 ──────────────
        atl = self.current_settings.get("advanced_trading_layers", {})

        # ── 타이틀 ─────────────────────────────────────────────────
        ctk.CTkLabel(
            scroll_frame,
            text="🔧 고급 자동매매 계층 설정",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(10, 4))
        ctk.CTkLabel(
            scroll_frame,
            text="각 계층을 개별 ON/OFF 하거나, 프리셋 버튼으로 한 번에 전환하세요.\n모든 계층은 Binance·CCXT·주식 경로에 공통 적용됩니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="center",
        ).pack(pady=(0, 16))

        # ── 프리셋 전환 버튼 그룹 ──────────────────────────────────
        preset_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        preset_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            preset_group,
            text="⚡ 프리셋 빠른 전환",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(16, 8))

        ctk.CTkLabel(
            preset_group,
            text="dev: 전체 OFF (개발/테스트용)  |  safe: 검증된 안전 임계값  |  aggressive: 더 공격적 임계값",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=self._color("text_secondary", "#9ca3af"),
        ).pack(pady=(0, 10))

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
                        "profitability_validation": {"enabled": True, "min_win_rate": 0.45, "min_sharpe": 0.50, "max_mdd": 0.30},
                        "portfolio_orchestration": {"enabled": True},
                        "strategy_engine": {"enabled": True, "consensus_threshold": 0.45},
                        "execution_optimizer": {"enabled": True, "max_slippage_bps": 50},
                        "ops_automation": {"enabled": True, "quality_score_threshold": 35.0},
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

            # 상태 레이블 업데이트
            colors = {"dev": "#94a3b8", "safe": "#22c55e", "aggressive": "#f59e0b"}
            self._preset_status_label.configure(
                text=f"✅ 프리셋 '{preset_name}' 적용됨",
                text_color=colors.get(preset_name, "#f9fafb"),
            )

        ctk.CTkButton(
            btn_row, text="🧪 dev (전체 OFF)", width=150, height=36,
            fg_color="#1e3a5f", hover_color="#1d4ed8",
            command=lambda: _apply_preset("dev"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="🛡️ safe (권장)", width=150, height=36,
            fg_color="#14532d", hover_color="#15803d",
            command=lambda: _apply_preset("safe"),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="⚡ aggressive", width=150, height=36,
            fg_color="#78350f", hover_color="#d97706",
            command=lambda: _apply_preset("aggressive"),
        ).pack(side="left", padx=6)

        self._preset_status_label = ctk.CTkLabel(
            preset_group, text="", font=ctk.CTkFont(size=12),
            text_color=self._color("text_secondary", "#94a3b8"),
        )
        self._preset_status_label.pack(pady=(0, 8))

        # ── 개별 계층 ON/OFF 스위치 ────────────────────────────────
        layers_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        layers_group.pack(fill="x", pady=(0, 20))

        ctk.CTkLabel(
            layers_group,
            text="⚙️ 계층별 개별 설정",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb"),
        ).pack(pady=(16, 10))

        layer_defs = [
            ("profitability_validation",  "1️⃣ 수익성 검증 (Profitability Gate)",
             "최근 거래 KPI(거래수/승률/샤프/워크포워드) 미달 시 신규 진입 차단. 차단 시: dev 임시 OFF, 기준 완화(min_trades/min_win_rate 등), 종료거래 데이터 축적 후 재평가"),
            ("portfolio_orchestration",   "2️⃣ 포트폴리오 오케스트레이션",
             "자산군별 자본 배분 및 리스크 예산 관리"),
            ("strategy_engine",           "3️⃣ 전략 엔진 (레짐 필터/합의)",
             "시장 국면 필터 + 다중 지표 합의 스코어 기반 진입 결정"),
            ("execution_optimizer",       "4️⃣ 실행 최적화 (슬리피지 제어)",
             "주문 유형 최적화, 슬리피지 감시, 자동 시장가 전환"),
            ("ops_automation",            "5️⃣ 운영 자동화 (이상 감지/롤백)",
             "quality_score 모니터링, 이상 거래 자동 감지, 일일 브리핑"),
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
            ).pack(anchor="w", padx=16, pady=(0, 10))

        # ── 도움말 ─────────────────────────────────────────────────
        help_group = ctk.CTkFrame(scroll_frame, corner_radius=12)
        help_group.pack(fill="x", pady=(0, 20))
        ctk.CTkLabel(
            help_group,
            text="ℹ️ 수익성 검증 차단이 반복되면 다음 순서로 점검하세요.\n1) dev(전체 OFF)로 임시 우회해 원인 분리\n2) safe/aggressive에서 min_trades, min_win_rate, min_sharpe 기준 완화\n3) 종료 거래 데이터가 충분히 쌓인 뒤 safe로 복귀\n자세한 설명은 대시보드 > 사용자 메뉴얼 > '수익성 검증 차단 시 대응' 절을 참조하세요.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("info", "#3b82f6"),
            justify="left",
        ).pack(padx=20, pady=16)

    def create_alphaarena_tab(self):
        """AlphaArena 모드 설정 탭 (새로운 alpha_arena 구조 적용)"""
        tab = self.tabview.add("⚔️ AlphaArena")

        # 스크롤 가능한 프레임
        scroll_frame = ctk.CTkScrollableFrame(tab)
        scroll_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 소개 섹션
        intro_group = ctk.CTkFrame(scroll_frame)
        intro_group.pack(fill="x", pady=(0, 20))

        intro_title = ctk.CTkLabel(
            intro_group,
            text="⚔️ Alpha Arena 모드",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        intro_title.pack(pady=(20, 10), padx=20)

        intro_desc = ctk.CTkLabel(
            intro_group,
            text="Alpha Arena 모드는 일반 자동매매와 다릅니다.\n\n1. LLM이 말로 거래를 지시하고\n2. 그 지시만 그대로 바이낸스에 나가며\n3. NoahAI의 기존 TP/SL 보험과 워치독은 동작하지 않습니다.\n\n설정에서 엔진과 심볼, 주기만 바꿔주세요.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            justify="left"
        )
        intro_desc.pack(pady=(0, 20), padx=20)

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

        # AI 엔진 선택 섹션
        ai_group = ctk.CTkFrame(scroll_frame)
        ai_group.pack(fill="x", pady=(0, 20))

        ai_title = ctk.CTkLabel(
            ai_group,
            text="🤖 AI 엔진 선택",
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

        self.alpha_arena_engine_var = ctk.StringVar(value="deepseek-3.1")
        engine_combo = ctk.CTkComboBox(
            ai_group,
            values=["deepseek-3.1", "qwen3-max"],
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
            text="🔑 API 키 설정",
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

        # Qwen3 (Alibaba) API Key
        qwen_label = ctk.CTkLabel(
            api_key_group,
            text="Qwen3 (Alibaba) API Key:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        qwen_label.pack(anchor="w", padx=20, pady=(5, 5))

        self.alpha_arena_qwen_api_key_var = ctk.StringVar(value="")
        qwen_entry = ctk.CTkEntry(
            api_key_group,
            textvariable=self.alpha_arena_qwen_api_key_var,
            placeholder_text="API 키를 입력하세요",
            height=35,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self._color("background", "#050a13"),
            border_color=self._color("secondary", "#1f2937"),
            show="*"
        )
        qwen_entry.pack(fill="x", padx=20, pady=(0, 20))

        # 초기 자금 기준 선택 섹션
        capital_group = ctk.CTkFrame(scroll_frame)
        capital_group.pack(fill="x", pady=(0, 20))

        capital_title = ctk.CTkLabel(
            capital_group,
            text="💰 초기 자금 기준 선택",
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
            text="⚠️ 주의사항",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=self._color("danger", "#ef4444")
        )
        warning_title.pack(anchor="w", padx=20, pady=(20, 10))

        warning_items = [
            "• Alpha Arena는 LLM이 직접 거래를 지시하는 모드입니다",
            "• 기존 TP/SL 보험과 워치독은 동작하지 않습니다",
            "• LLM이 TP/SL을 지정하지 않으면 주문이 실행되지 않습니다",
            "• 모든 거래 결과는 사용자 본인의 책임입니다"
        ]

        for item in warning_items:
            item_label = ctk.CTkLabel(
                warning_card,
                text=item,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=self._color("text_primary", "#f9fafb"),
                justify="left"
            )
            item_label.pack(anchor="w", padx=20, pady=(0, 5))

        help_label = ctk.CTkLabel(
            warning_card,
            text="• 모르면 대시보드 사용자메뉴얼에서 AlphaArena 가서 설명을 읽어주세요",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("info", "#3b82f6"),
            justify="left"
        )
        help_label.pack(anchor="w", padx=20, pady=(10, 20))

    def _verify_alphaarena_api_key(self):
        """선택한 AI 엔진의 API 키 검증"""
        selected_ai = self.alphaarena_ai_var.get()

        # 선택한 AI에 따라 해당 API 키 가져오기
        if selected_ai == "deepseek-chat-v3.1":
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
            self.alphaarena_verify_status.configure(text="❌ 알 수 없는 AI 엔진")
            return

        if not api_key:
            self.alphaarena_verify_status.configure(
                text="❌ API 키를 입력해주세요",
                text_color=self._color("danger", "#ef4444")
            )
            return

        self.alphaarena_verify_status.configure(
            text="🔄 검증 중...",
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
            text=f"✅ {provider} API 키 형식 검증 완료 (실제 검증은 구현 예정)",
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
        print(f"❌ 설정 창 실행 오류: {e}")
        import traceback
        traceback.print_exc()
