#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
현대적 로그인 창 (CustomTkinter 기반)
고정 스킨 디자인 (테마 시스템 제거됨)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import sys
import os
import json
import webbrowser
import requests
from datetime import datetime
from PIL import Image
from api.kpi_client import emit_kpi_event

# 고정 색상 import
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.fixed_colors import FIXED_COLORS

# CustomTkinter 5.1.3 - dark 모드 정상 작동
ctk.set_appearance_mode("dark")

class LoginWindow:
    """현대적 로그인 창 - 고정 스킨"""

    def __init__(self, parent=None):
        self.parent = parent
        self.root = ctk.CTk() if parent is None else ctk.CTkToplevel(parent)
        try:
            from ui.typography import configure_platform_typography
            from utils.runtime_stability import install_tk_exception_hook

            configure_platform_typography(self.root)
            install_tk_exception_hook(self.root)
        except Exception:
            pass
        self.root.title("NoahAI Finance Decision OS - 로그인")
        self.root.geometry("450x680")
        self.root.resizable(False, False)
        self.root.configure(fg_color=self._color("background", "#050a13"))

        # 백엔드 URL 설정
        self.backend_url = "https://daltrading.net/auth/api_login"

        # 파일 경로 설정
        self.setup_file_paths()

        # 로그인 정보 저장 변수
        self.save_login_var = ctk.BooleanVar()

        # 안전 종료를 위한 after() 작업 추적
        self.after_jobs = []
        self._is_destroying = False

        # 콜백 함수들 (PyQt5 시그널 대신)
        self.login_success_callback = None

        # UI 설정
        self.setup_ui()

        # 저장된 로그인 정보 로드
        self.load_saved_credentials()

        # 안전 종료를 위한 프로토콜 설정
        self.root.protocol("WM_DELETE_WINDOW", self.close_safely)

        # 중앙 정렬
        self.center_window()

    def connect_login_success(self, callback):
        """로그인 성공 콜백 연결 (PyQt5 시그널 대신)"""
        self.login_success_callback = callback

    def login_success(self):
        """로그인 성공 시그널 (PyQt5 호환성)"""
        if self.login_success_callback:
            try:
                # 토큰과 사용자 정보를 콜백으로 전달
                token_data = self.load_token_data()
                if token_data:
                    self.login_success_callback(token_data['access_token'], token_data['user_info'])
                else:
                    print("토큰 데이터를 로드할 수 없습니다.")
            except Exception as e:
                print(f"로그인 성공 콜백 오류: {e}")

    def setup_file_paths(self):
        """파일 경로 설정 - 자동 로그인을 위한 credentials 파일만 로드"""
        try:
            from path_utils import get_credentials_file_path, get_account_info_from_token, set_current_user_account

            # 기존 계정 정보 확인
            user_id, token_path = get_account_info_from_token()
            if user_id:
                # 사용자 계정 설정
                set_current_user_account(user_id)
                # path_utils를 사용하여 올바른 경로 가져오기
                self.credentials_file = get_credentials_file_path()
            else:
                self.credentials_file = None
        except Exception as e:
            print(f"path_utils 사용 실패: {e}")
            self.credentials_file = None

    def setup_ui(self):
        """UI 설정"""
        # 메인 컨테이너
        main_frame = ctk.CTkFrame(self.root, fg_color=self._color("background", "#050a13"))
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # 로고 영역
        self.create_logo_section(main_frame)

        # 로그인 폼 영역
        self.create_login_form(main_frame)

        # 하단 정보 영역
        self.create_footer_section(main_frame)

    def _color(self, key: str, fallback: str = "#9ca3af") -> str:
        """고정 색상 접근 헬퍼"""
        return FIXED_COLORS.get(key, fallback)

    def create_logo_section(self, parent):
        """로고 섹션 생성"""
        logo_frame = ctk.CTkFrame(parent, fg_color=self._color("background", "#050a13"))
        logo_frame.pack(fill="x", pady=(20, 30))

        # 브랜드 로고 + 타이틀 행
        title_row = ctk.CTkFrame(logo_frame, fg_color=self._color("background", "#050a13"))
        title_row.pack(pady=(0, 10))

        try:
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icon.png')
            logo_img = Image.open(logo_path)

            # 원본 비율 유지: 타이틀 글자 높이(약 30px)에 맞춰 로고 크기 계산
            src_w, src_h = logo_img.size
            target_h = 28
            target_w = max(1, int(src_w * (target_h / max(1, src_h))))
            self.login_logo_image = ctk.CTkImage(
                light_image=logo_img,
                dark_image=logo_img,
                size=(target_w, target_h)
            )

            logo_icon_label = ctk.CTkLabel(
                title_row,
                text="",
                image=self.login_logo_image,
                fg_color="transparent"
            )
            logo_icon_label.pack(side="left", padx=(0, 8))
        except Exception:
            # 로고 로드 실패 시에도 타이틀 텍스트는 표시한다.
            pass

        # 메인 로고
        logo_label = ctk.CTkLabel(
            title_row,
            text="NoahAI Decision OS",
            font=ctk.CTkFont(family="Segoe UI", size=32, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        logo_label.pack(side="left")

        # 부제목
        subtitle_label = ctk.CTkLabel(
            logo_frame,
            text="AI 재테크 의사결정 파트너",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        subtitle_label.pack()

        # 버전 정보 (제거됨 - 불필요한 정보)

    def create_login_form(self, parent):
        """로그인 폼 생성"""
        form_frame = ctk.CTkFrame(
            parent,
            fg_color=self._color("surface", "#0b1120"),
            border_color=self._color("border", "#1e293b"),
            border_width=2,
            corner_radius=12
        )
        form_frame.pack(fill="both", expand=True, pady=(0, 15))

        # 폼 제목
        form_title = ctk.CTkLabel(
            form_frame,
            text="로그인",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        form_title.pack(pady=(30, 20))

        # 아이디 입력
        id_label = ctk.CTkLabel(
            form_frame,
            text="아이디",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        id_label.pack(anchor="w", padx=40, pady=(15, 8))

        self.id_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="아이디를 입력하세요",
            height=50,
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("border", "#1e293b"),
            border_width=1,
            corner_radius=8
        )
        self.id_entry.pack(fill="x", padx=40, pady=(0, 15))

        # 패스워드 입력
        password_label = ctk.CTkLabel(
            form_frame,
            text="패스워드",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        password_label.pack(anchor="w", padx=40, pady=(0, 8))

        self.password_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="패스워드를 입력하세요",
            height=50,
            show="*",
            font=ctk.CTkFont(family="Segoe UI", size=14),
            fg_color=self._color("background", "#050a13"),
            text_color=self._color("text_primary", "#f9fafb"),
            border_color=self._color("border", "#1e293b"),
            border_width=1,
            corner_radius=8
        )
        self.password_entry.pack(fill="x", padx=40, pady=(0, 15))

        # 로그인 정보 저장 + 도움말 버튼 행
        save_row = ctk.CTkFrame(form_frame, fg_color=self._color("surface", "#0b1120"))
        save_row.pack(fill="x", padx=40, pady=(5, 25))

        self.save_login_checkbox = ctk.CTkCheckBox(
            save_row,
            text="로그인 정보 저장",
            variable=self.save_login_var,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=self._color("text_secondary", "#9ca3af"),
            fg_color=self._color("primary", "#1f6feb"),
            hover_color=self._color("primary", "#1f6feb")
        )
        self.save_login_checkbox.pack(side="left", pady=5)

        help_button_inline = ctk.CTkButton(
            save_row,
            text="도움말",
            width=90,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color=self._color("secondary", "#374151"),
            text_color=self._color("text_secondary", "#9ca3af"),
            hover_color=self._color("info", "#3b82f6"),
            corner_radius=8,
            command=self.show_help
        )
        help_button_inline.pack(side="right", padx=(10, 0), pady=5)

        # 로그인/회원가입 버튼 영역
        button_frame = ctk.CTkFrame(form_frame, fg_color=self._color("surface", "#0b1120"))
        button_frame.pack(fill="x", padx=40, pady=(0, 30))

        # 회원가입 버튼
        signup_button = ctk.CTkButton(
            button_frame,
            text="회원가입",
            height=48,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=self._color("secondary", "#6b7280"),
            text_color="white",
            hover_color="#4b5563",
            corner_radius=10,
            command=self.signup
        )
        signup_button.pack(side="left", fill="x", expand=True, padx=(0, 8))

        # 로그인 버튼
        login_button = ctk.CTkButton(
            button_frame,
            text="로그인",
            height=48,
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            fg_color=self._color("success", "#10b981"),
            text_color="white",
            hover_color="#059669",
            corner_radius=10,
            command=self.login
        )
        login_button.pack(side="right", fill="x", expand=True)

    def create_footer_section(self, parent):
        """하단 여백 (안내·링크는 「도움말」 탭으로 통합)"""
        footer_frame = ctk.CTkFrame(parent, fg_color=self._color("background", "#050a13"))
        footer_frame.pack(fill="x", pady=(6, 0))

    def open_noahai_product_page(self):
        webbrowser.open("https://noahailabs.com/ko/product")

    def open_noahai_about_page(self):
        webbrowser.open("https://noahailabs.com/ko/about")

    def open_noahai_technology_page(self):
        webbrowser.open("https://noahailabs.com/ko/technology")

    def open_noahai_financial_ai_future_page(self):
        webbrowser.open("https://noahailabs.com/ko/service/financial-ai-future")

    def center_window(self):
        """창을 화면 중앙에 배치"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (450 // 2)
        y = (self.root.winfo_screenheight() // 2) - (680 // 2)
        self.root.geometry(f"450x680+{x}+{y}")

    def login(self):
        """로그인 처리"""
        user_id = self.id_entry.get().strip()
        password = self.password_entry.get().strip()
        save_login = self.save_login_var.get()

        # 패스워드가 별표로 표시된 경우 실제 패스워드 로드
        if password == "********":
            try:
                if self.credentials_file and os.path.exists(self.credentials_file):
                    with open(self.credentials_file, 'r', encoding='utf-8') as f:
                        credentials = json.load(f)
                    password = credentials.get('password', '')
                    print(f"저장된 패스워드 사용: {'*' * len(password)}")
                else:
                    print("credentials_file이 없거나 설정되지 않았습니다.")
                    messagebox.showerror("오류", "저장된 로그인 정보가 없습니다.")
                    return
            except Exception as e:
                print(f"저장된 패스워드 로드 실패: {e}")
                messagebox.showerror("오류", "저장된 패스워드를 로드할 수 없습니다.")
                return

        if not user_id or not password:
            messagebox.showerror("오류", "아이디와 패스워드를 모두 입력해주세요.")
            return

        # 로딩 상태 표시
        self.show_loading()

        try:
            # 백엔드 API 호출
            response = self.call_login_api(user_id, password)

            # 서버 응답에 access_token이 있으면 로그인 성공
            if response.get('access_token'):
                token = response.get('access_token')
                user_info = {
                    'id': response.get('id'),
                    'email': response.get('email'),
                    'session_id': response.get('session_id'),
                    'token_type': response.get('token_type'),
                    'user_grade': response.get('user_grade', 'pro_coin'),
                    'membership_policy': response.get('membership_policy', {})
                }

                # 로그인 정보 저장 (아이디 + 패스워드)
                if hasattr(self, 'save_credentials'):
                    try:
                        # API 호출에 사용한 진짜 평문 패스워드 사용
                        if password:
                            self.save_credentials(user_id, password)
                    except Exception as e:
                        print(f"로그인 정보 저장 실패: {e}")

                # main.py의 콜백 호출하여 파일 생성
                if self.login_success_callback:
                    try:
                        self.login_success_callback(token, user_info)
                    except Exception as e:
                        import traceback
                        print(f"main.py 콜백 호출 실패: {e}")
                        print(traceback.format_exc())

                # 로그인 성공
                self.login_complete()

            else:
                self.loading_frame.destroy()
                error_msg = response.get('detail', '로그인에 실패했습니다.')
                messagebox.showerror("로그인 실패", error_msg)

        except Exception as e:
            self.loading_frame.destroy()
            messagebox.showerror("오류", f"로그인 중 오류가 발생했습니다: {str(e)}")

    def call_login_api(self, username, password):
        """로그인 API 호출"""
        try:
            # 기존 로그인 창과 동일한 방식으로 수정
            data = {
                'id': username,  # username을 id로 변경
                'password': password
            }

            headers = {
                'Content-Type': 'application/json'
            }

            print(f"로그인 API 호출: {self.backend_url}")
            print(f"전송 데이터: {{'id': '{username}', 'password': '********'}}")  # 표시만 마스킹

            response = requests.post(
                self.backend_url,
                json=data,
                headers=headers,
                timeout=10
            )

            print(f"응답 상태 코드: {response.status_code}")

            if response.status_code == 200:
                response_data = response.json()
                print(f"로그인 성공 응답: {response_data}")
                emit_kpi_event(
                    event_type="login_success_api",
                    category="auth",
                    asset_class="platform",
                    status="success",
                    source="noahai_client_login",
                    metadata={
                        "channel": "desktop_client",
                        "user_id": username,
                    },
                )
                return response_data
            else:
                # 400 오류 시 응답 내용도 출력
                try:
                    error_detail = response.json()
                    print(f"오류 응답 내용: {error_detail}")
                    emit_kpi_event(
                        event_type="login_failed",
                        category="auth",
                        asset_class="platform",
                        status="failed",
                        source="noahai_client_login",
                        metadata={
                            "channel": "desktop_client",
                            "user_id": username,
                            "http_status": response.status_code,
                        },
                    )
                    return {'detail': f'API 호출 실패: {response.status_code} - {error_detail}'}
                except:
                    print(f"응답 텍스트: {response.text}")
                    emit_kpi_event(
                        event_type="login_failed",
                        category="auth",
                        asset_class="platform",
                        status="failed",
                        source="noahai_client_login",
                        metadata={
                            "channel": "desktop_client",
                            "user_id": username,
                            "http_status": response.status_code,
                        },
                    )
                    return {'detail': f'API 호출 실패: {response.status_code} - {response.text}'}

        except requests.exceptions.RequestException as e:
            emit_kpi_event(
                event_type="login_failed",
                category="auth",
                asset_class="platform",
                status="failed",
                source="noahai_client_login",
                metadata={
                    "channel": "desktop_client",
                    "user_id": username,
                    "error_type": "network_error",
                },
            )
            return {'detail': f'네트워크 오류: {str(e)}'}
        except Exception as e:
            emit_kpi_event(
                event_type="login_failed",
                category="auth",
                asset_class="platform",
                status="failed",
                source="noahai_client_login",
                metadata={
                    "channel": "desktop_client",
                    "user_id": username,
                    "error_type": "unexpected_error",
                },
            )
            return {'detail': f'예상치 못한 오류: {str(e)}'}

    def load_saved_credentials(self):
        """저장된 로그인 정보 로드"""
        try:
            if self.credentials_file and os.path.exists(self.credentials_file):
                with open(self.credentials_file, 'r', encoding='utf-8') as f:
                    credentials = json.load(f)

                username = credentials.get('username', '')
                password = credentials.get('password', '')

                if username:
                    self.id_entry.insert(0, username)
                    self.save_login_var.set(True)
                    print(f"저장된 로그인 정보 로드: {username}")

                if password:
                    # 패스워드를 별표로 표시하여 사용자에게 저장된 것을 알림
                    self.password_entry.insert(0, "********")
                    print(f"저장된 패스워드 로드: {'*' * len(password)}")

        except Exception as e:
            print(f"로그인 정보 로드 실패: {e}")

    def save_credentials(self, username, password):
        """로그인 정보 저장 (자동 로그인 활성화)"""
        try:
            # 방어막: 플레이스홀더 패스워드는 저장하지 않기
            if password == "********":
                print("placeholder 패스워드는 저장하지 않습니다.")
                return

            # path_utils를 사용하여 올바른 경로에 저장
            from path_utils import get_credentials_file_path, set_current_user_account

            # 사용자 계정 설정
            set_current_user_account(username)

            # 올바른 경로에서 credentials 파일 경로 가져오기
            credentials_file_path = get_credentials_file_path()

            credentials = {
                'username': username,
                'password': password,
                'auto_login': True,  # 자동 로그인 활성화
                'saved_at': datetime.now().isoformat()
            }

            # 디렉토리 생성
            os.makedirs(os.path.dirname(credentials_file_path), exist_ok=True)

            with open(credentials_file_path, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, ensure_ascii=False, indent=2)

            print(f"로그인 정보 저장 (자동 로그인 활성화): {username} -> {credentials_file_path}")

        except Exception as e:
            print(f"로그인 정보 저장 실패: {e}")

    def signup(self):
        """회원가입 처리 - 웹사이트로 연결"""
        import webbrowser

        # 회원가입 웹사이트 URL
        signup_url = "https://daltrading.net"

        try:
            # 웹브라우저로 회원가입 페이지 열기
            webbrowser.open(signup_url)
            messagebox.showinfo(
                "회원가입",
                f"회원가입 페이지로 이동합니다.\n\n{signup_url}\n\n"
                "가입 시 운영 정책에 따라 가입키(초대/인증 키)가 필요할 수 있습니다.\n"
                "가입키가 필요한 경우 판매 채널 또는 공식 고객지원 경로에서 발급받아 입력해주세요.\n\n"
                "회원가입 완료 후 앱으로 돌아와 로그인해주세요."
            )
        except Exception as e:
            messagebox.showerror("오류", f"웹사이트를 열 수 없습니다: {str(e)}")

    def save_login_info(self, user_id, password):
        """로그인 정보 저장"""
        try:
            if not self.credentials_file:
                print("credentials_file 경로가 설정되지 않았습니다.")
                return

            credentials = {
                "user_id": user_id,
                "password": password,
                "saved_at": datetime.now().isoformat()
            }

            # 디렉토리 생성
            os.makedirs(os.path.dirname(self.credentials_file), exist_ok=True)

            with open(self.credentials_file, 'w', encoding='utf-8') as f:
                json.dump(credentials, f, ensure_ascii=False, indent=2)
            print(f"로그인 정보 저장: {user_id}")
        except Exception as e:
            print(f"로그인 정보 저장 실패: {e}")

    def show_loading(self):
        """로딩 상태 표시"""
        # 로딩 오버레이 - CustomTkinter에서 지원하는 색상 사용
        self.loading_frame = ctk.CTkFrame(self.root, fg_color="#000000")
        self.loading_frame.place(relx=0.5, rely=0.5, anchor="center")

        loading_label = ctk.CTkLabel(
            self.loading_frame,
            text="로그인 중...",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="normal"),
            text_color="white"
        )
        loading_label.pack(pady=25)

    def login_complete(self):
        """로그인 완료 처리 - main.py에서 로그인창을 닫으므로 여기서는 아무것도 하지 않음"""
        pass

    def load_token_data(self):
        """토큰 데이터 로드 - 사용자 폴더의 token.json에서 읽기"""
        try:
            # path_utils를 사용하여 올바른 경로에서 token.json 읽기
            from path_utils import get_token_file_path
            token_file_path = get_token_file_path()

            if os.path.exists(token_file_path):
                with open(token_file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"토큰 파일이 없습니다: {token_file_path}")
        except Exception as e:
            print(f"토큰 데이터 로드 실패: {e}")
        return None

    def open_dashboard(self):
        """대시보드 열기 - 새로운 CustomTkinter 대시보드"""
        # main.py에서 닫을 것이므로 여기서는 닫지 않음
        # self.root.destroy()

        # 대시보드 실행
        try:
            # 새로운 CustomTkinter 대시보드 실행
            from ui.dashboard_modern import ModernDashboard
            from trading.exchange_manager import ExchangeManager
            from config.settings import load_settings

            # 설정 로드
            settings = load_settings()

            # main.py를 통해 대시보드 실행 (main_app 연결을 위해)
            from main import NoahAIClient
            client = NoahAIClient()
            client.start()

        except ImportError as e:
            print(f"대시보드 실행 실패: {e}")
            messagebox.showerror("오류", "대시보드를 실행할 수 없습니다.")
        except Exception as e:
            print(f"대시보드 실행 실패: {e}")
            messagebox.showerror("오류", f"대시보드 실행 중 오류가 발생했습니다: {str(e)}")

    def show_help(self):
        """도움말: 로그인 안내·이용·책임 참고·공식 웹 링크를 탭으로 통합"""
        help_window = ctk.CTkToplevel(self.root)
        help_window.title("도움말")
        help_window.geometry("640x540")
        help_window.transient(self.root)
        help_window.resizable(True, True)

        outer = ctk.CTkFrame(help_window, fg_color=self._color("background", "#050a13"))
        outer.pack(fill="both", expand=True, padx=12, pady=12)

        tabs = ctk.CTkTabview(outer)
        tabs.pack(fill="both", expand=True, padx=4, pady=(0, 8))

        # --- 탭 1: 로그인 ---
        t_login = tabs.add("로그인 안내")
        tb1 = ctk.CTkTextbox(
            t_login,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            wrap="word",
        )
        tb1.pack(fill="both", expand=True, padx=8, pady=8)
        tb1.insert(
            "1.0",
            """
NoahAI Decision OS — 로그인

1) 아이디·패스워드
   • 가입 시 등록한 계정으로 로그인합니다.
   • 「로그인 정보 저장」을 켜두면 다음 실행 시 아이디가 채워질 수 있습니다.

2) 회원가입
    • 「회원가입」 버튼을 누르면 웹(https://daltrading.net)으로 이동합니다.
    • 웹에서 회원가입을 완료한 뒤, 이 화면으로 돌아와 다시 로그인합니다.
    • 운영 정책에 따라 가입키(초대/인증 키)가 필요한 계정은
      판매 채널 또는 공식 고객지원 경로에서 발급받아 입력합니다.
   • 약관·필수 동의는 회원가입(웹) 절차에서 진행하는 것을 권장합니다.

3) 보안
   • 충분히 긴 패스워드 사용, 주기적 변경을 권장합니다.
   • 의심스러운 접근이 있으면 비밀번호를 바꾸고 지원 채널로 문의하세요.

4) 기타
   • 본 앱은 고정 스킨 UI를 사용합니다.
    • 문의는 고객지원 채널을 이용해 주세요.
    • 이용·책임 관련 참고 문구는 「이용·책임 참고」 탭에서 확인할 수 있습니다.
""".strip(),
        )
        tb1.configure(state="disabled")

        # --- 탭 2: 이용·책임 (참고용, 로그인할 때마다 동의하지 않음) ---
        t_policy = tabs.add("이용·책임 참고")
        tb2 = ctk.CTkTextbox(
            t_policy,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            wrap="word",
        )
        tb2.pack(fill="both", expand=True, padx=8, pady=8)
        tb2.insert(
            "1.0",
            """
참고용 안내 (로그인할 때마다 동의 절차를 두지 않습니다)

1) 서비스 성격
   • 베타·테스트 성격의 기능이 포함될 수 있습니다.
   • NoahAI는 투자·금융 자문이 아니며, AI가 제공하는 분석·판단 정보는 참고용입니다.
   • 최종 금융 결정과 그 결과는 사용자 본인 책임입니다.

2) 역할 구분
   • 앱: 판단·설명·기록·검증·환류를 돕는 인프라에 가깝습니다.
   • 주문·체결·자금 이동: 사용자 계정과 거래소·증권사 등 외부 API가 수행합니다.

3) 약관·동의
   • 필수 약관·동의는 회원가입(또는 운영 정책이 정한 최초 1회 절차)에서 처리하는 것을 전제로 합니다.
   • 이 탭은 로그인 전에도 내용을 미리 읽어 보실 수 있도록 제공하는 참고 문구입니다.

4) 손실·장애
   • 시장 변동, API 오류, 거래소 장애 등 실행 구간 이슈의 1차 책임은
     사용자 및 외부 서비스 제공자에 있습니다.

5) XAI·규제 정렬
   • 판단 근거를 로그·화면으로 추적할 수 있게 하는 방향을 지향합니다.
   • AI 기본법 등 국내 규제 환경에 맞춰 문구·기능을 고도화합니다.

로그인 후 앱 메뉴얼 「이용 안내·책임」에서 항목별 전문을 확인할 수 있습니다.
""".strip(),
        )
        tb2.configure(state="disabled")

        # --- 탭 3: 공식 웹 ---
        t_web = tabs.add("공식 안내(웹)")
        web_frame = ctk.CTkFrame(t_web, fg_color="transparent")
        web_frame.pack(fill="both", expand=True, padx=12, pady=12)

        intro = ctk.CTkLabel(
            web_frame,
            text="Noah AI Labs 공식 사이트에서 회사 소개 → 서비스·적용 영역 → 기술 소개 → 금융 AI와 미래 순서로 확인할 수 있습니다.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=self._color("text_secondary", "#9ca3af"),
            wraplength=520,
            justify="left",
        )
        intro.pack(anchor="w", pady=(0, 12))

        btn_style = {
            "height": 36,
            "font": ctk.CTkFont(family="Segoe UI", size=13),
            "fg_color": self._color("secondary", "#374151"),
            "hover_color": self._color("info", "#3b82f6"),
            "corner_radius": 8,
        }
        ctk.CTkButton(
            web_frame,
            text="회사 소개",
            command=self.open_noahai_about_page,
            **btn_style,
        ).pack(fill="x", pady=4)
        ctk.CTkButton(
            web_frame,
            text="서비스·적용 영역",
            command=self.open_noahai_product_page,
            **btn_style,
        ).pack(fill="x", pady=4)
        ctk.CTkButton(
            web_frame,
            text="기술 소개",
            command=self.open_noahai_technology_page,
            **btn_style,
        ).pack(fill="x", pady=4)
        ctk.CTkButton(
            web_frame,
            text="금융 AI와 미래",
            command=self.open_noahai_financial_ai_future_page,
            **btn_style,
        ).pack(fill="x", pady=4)

        ctk.CTkButton(
            outer,
            text="닫기",
            width=100,
            command=help_window.destroy,
        ).pack(side="right", pady=(0, 4))

    def open_settings(self):
        """설정 창 열기"""
        settings_window = ctk.CTkToplevel(self.root)
        settings_window.title("설정")
        settings_window.geometry("500x400")
        settings_window.transient(self.root)

        # 설정 메시지 (테마 시스템 제거됨)
        info_frame = ctk.CTkFrame(settings_window)
        info_frame.pack(fill="x", padx=25, pady=25)

        info_label = ctk.CTkLabel(
            info_frame,
            text="테마 설정",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=self._color("text_primary", "#f9fafb")
        )
        info_label.pack(pady=(20, 15))

        message_label = ctk.CTkLabel(
            info_frame,
            text="현재 고정 스킨 디자인이 적용되어 있습니다.\n테마 변경은 지원하지 않습니다.",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="normal"),
            text_color=self._color("text_secondary", "#9ca3af")
        )
        message_label.pack(pady=(0, 20))

    def apply_theme(self, theme_name):
        """테마 적용 (더 이상 사용되지 않음)"""
        pass

    def safe_after(self, delay, func, *args, **kwargs):
        """안전한 after() 메서드 - 작업 추적"""
        try:
            if self._is_destroying or not self.root.winfo_exists():
                return None
            job_id = self.root.after(delay, func, *args, **kwargs)
            if job_id:
                self.after_jobs.append(job_id)
            return job_id
        except Exception as e:
            print(f"LoginWindow safe_after 오류: {e}")
            return None

    def cleanup_after_jobs(self):
        """모든 after() 작업 정리"""
        try:
            if not self.root.winfo_exists():
                return
            for job_id in self.after_jobs:
                try:
                    self.root.after_cancel(job_id)
                except:
                    pass
            self.after_jobs.clear()
            # Tkinter의 모든 after() 작업 취소 시도
            try:
                self.root.tk.call('after', 'cancel', 'all')
            except:
                pass
        except:
            pass

    def close_safely(self):
        """안전한 종료"""
        try:
            self._is_destroying = True
            self.cleanup_after_jobs()
            try:
                self.root.withdraw()
                self.root.quit()
            except:
                pass
            try:
                self.root.destroy()
            except:
                pass
        except Exception as e:
            print(f"LoginWindow 안전 종료 오류: {e}")

    def run(self):
        """UI 실행"""
        self.root.mainloop()

    def validate_token(self, access_token):
        """토큰 유효성 검증 (JWT 토큰 디코딩)"""
        try:
            import base64
            import json

            # JWT 토큰 디코딩 (간단한 방법)
            # JWT는 .으로 구분된 3부분: header.payload.signature
            parts = access_token.split('.')
            if len(parts) != 3:
                print("잘못된 JWT 토큰 형식")
                return False

            # payload 디코딩
            payload = parts[1]
            # Base64 패딩 추가
            payload += '=' * (4 - len(payload) % 4)
            decoded_payload = base64.b64decode(payload)
            payload_data = json.loads(decoded_payload)

            # 만료 시간 확인
            exp = payload_data.get('exp', 0)
            current_time = int(datetime.now().timestamp())

            if exp > current_time:
                print(f"토큰 유효 (만료: {datetime.fromtimestamp(exp)})")
                return True
            else:
                print(f"토큰 만료됨 (만료: {datetime.fromtimestamp(exp)})")
                return False

        except Exception as e:
            print(f"토큰 검증 오류: {e}")
            return False

# 편의 함수
def show_login_window(parent=None):
    """로그인 창 표시"""
    login_window = LoginWindow(parent)
    login_window.run()
    return login_window

if __name__ == "__main__":
    try:
        app = LoginWindow()
        app.run()
    except ImportError:
        print("CustomTkinter가 설치되지 않았습니다.")
        print("다음 명령어로 설치하세요:")
        print("pip install customtkinter")
