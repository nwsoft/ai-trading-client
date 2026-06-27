    def create_status_bar(self):
        """상단 상태 바 생성 - 기존 카드형 구조"""
        # 🔥 완전 하드코딩 - 로그인 모달처럼
        self.status_frame = ctk.CTkFrame(
            self.main_frame,
            fg_color="#1d2433",
            border_color="#3a4559",
            border_width=2,
            corner_radius=12
        )
        status_frame = self.status_frame
        status_frame.pack(fill="x", pady=(0, 10))
        try:
            status_frame.grid_columnconfigure(0, weight=0)
            status_frame.grid_columnconfigure(1, weight=1)
            status_frame.grid_columnconfigure(2, weight=0)
        except Exception:
            pass

        # 좌측: 앱 제목과 사용자 정보
        left_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        try:
            left_frame.grid(column=0, row=0, sticky="w", padx=10, pady=10)
        except Exception:
            left_frame.pack(side="left", padx=10, pady=10)

        # 🔥 하드코딩
        title_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#2c3545",
            border_color="#3a4559",
            border_width=1,
            corner_radius=12,
            height=36
        )
        title_frame.pack(side="left", padx=(0, 20))
        self.app_title_label = ctk.CTkLabel(
            title_frame,
            text="🤝 NoahAI-AI 금융 동반자",
            font=self._get_safe_font("subheading", ctk.CTkFont(size=16, weight="bold")),
            fg_color="transparent",
            text_color="#f9fafb"
        )
        self.app_title_label.pack(fill="both", expand=True)

        # 🔥 하드코딩
        user_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#2c3545",
            border_color="#3a4559",
            border_width=1,
            corner_radius=12
        )
        user_frame.pack(side="left", padx=(0, 8))
        self.user_info_label = ctk.CTkLabel(
            user_frame,
            text="👤 사용자: 로딩 중...",
            font=self._get_safe_font("body", ctk.CTkFont(size=14, weight="bold")),
            fg_color="transparent",
            text_color="#f9fafb"
        )
        self.user_info_label.pack(fill="both", expand=True)

        # 🔥 하드코딩
        exchange_frame = ctk.CTkFrame(
            left_frame,
            fg_color="#2c3545",
            border_color="#3a4559",
            border_width=1,
            corner_radius=12,
            height=32
        )
        exchange_frame.pack(side="left", padx=(0, 8))
        self.exchange_info_label = ctk.CTkLabel(
            exchange_frame,
            text="🏦 거래소: binance",
            font=self._get_safe_font("body", ctk.CTkFont(size=14, weight="bold")),
            fg_color="transparent",
            text_color="#22c55e"
        )
        self.exchange_info_label.pack(fill="both", expand=True)

    def create_service_tabs(self, parent):
        """서비스 탭 버튼들 생성"""
        try:
            parent.configure(fg_color="transparent")
        except Exception:
            pass

        # 현재 활성 서비스 (기본값: 블록체인)
        self.current_service = getattr(self, 'current_service', "blockchain")

        # 🔥 완전 하드코딩
        active_fg = "#2563eb"
        active_text = "#ffffff"
        active_hover = "#1a5fd1"
        inactive_fg = "#3a5a7f"
        inactive_text = "#ffffff"
        inactive_hover = "#4a6a8f"

        tab_font = self._get_safe_font("button", ctk.CTkFont(size=14, weight="bold"))
