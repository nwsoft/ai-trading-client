from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Any, Callable, Dict, Iterable, List, Optional

import customtkinter as ctk

from trading.financial_intelligence import FinancialIntelligenceService
from ui.visual_system import style_tabview


class FinancialIntelligenceWidget(ctk.CTkFrame):
    """일반 사용자가 코드나 JSON 없이 사용하는 금융 분석 화면."""

    MODE_TABS = {
        "ai_analyst": ["글로벌 시장", "이벤트·속보", "내러티브", "산업·거시"],
        "stock": ["시장·섹터", "기업 분석", "가치평가", "종목 탐색", "지표 탐색", "전략 검증", "기관 동향"],
        "blockchain": ["시장·섹터", "코인 탐색", "지표 탐색", "전략 검증", "이벤트·속보"],
        "asset": ["성과·위험"],
    }

    FEATURE_GUIDES = {
        "시장 현황과 수익률": "프리셋 선택 → 시장 현황 조회 → 출처·기준시각 → 수익률·변동성 순으로 확인",
        "보유자산 일정과 속보": "일정·속보 확인 → 보유자산 관련 항목 → 발생 시각·출처 → 예상 영향 확인",
        "시장 내러티브": "내러티브 확인 → 반복 이슈 → 관련 자산 → 사실과 시장 해석을 분리해 확인",
        "산업·거시경제": "거시 환경 확인 → 경기 국면 → 자산군 영향 → 데이터 연결 상태 확인",
        "기업 재무분석": "DART/SEC 선택 → 기업 식별값·연도 입력 → 공시 재무 분석 → 출처 확인",
        "기업 가치평가": "현금흐름·주식 수·순부채 입력 → 시나리오 계산 → 가정별 범위를 비교",
        "종목 조건 검색": "관심 종목을 쉼표로 입력 → 최소 가격 설정 → 조건 검색 → 후보를 추가 검토",
        "기술지표": "종목 입력 → 지표 조회 → 차트와 RSI·MACD·이동평균의 방향·충돌을 함께 확인",
        "전략 검증": "종목·빠른/느린 평균 입력 → 전략 검증 실행 → 거래 수·비용·MDD를 함께 확인",
        "기관 보유 변화": "기관 동향 확인 → 신규·확대·축소 → 공시 기준일과 데이터 연결 상태 확인",
        "내 계좌 성과·위험": "내 성과 분석 → 거래 수 → 수수료 차감 성과 → MDD·집중도 순으로 확인",
    }

    MARKET_PRESETS = {
        "주요 시장": [
            {"symbol": "^KS11", "asset_type": "index"},
            {"symbol": "^GSPC", "asset_type": "index"},
            {"symbol": "^IXIC", "asset_type": "index"},
            {"symbol": "KRW=X", "asset_type": "fx"},
            {"symbol": "GC=F", "asset_type": "commodity"},
        ],
        "국내 시장": [
            {"symbol": "^KS11", "asset_type": "index"},
            {"symbol": "^KQ11", "asset_type": "index"},
            {"symbol": "005930.KS", "asset_type": "stock"},
            {"symbol": "000660.KS", "asset_type": "stock"},
        ],
        "미국 시장": [
            {"symbol": "^GSPC", "asset_type": "index"},
            {"symbol": "^IXIC", "asset_type": "index"},
            {"symbol": "AAPL", "asset_type": "stock"},
            {"symbol": "MSFT", "asset_type": "stock"},
        ],
        "가상자산": [
            {"symbol": "BTC", "asset_type": "crypto"},
            {"symbol": "ETH", "asset_type": "crypto"},
            {"symbol": "SOL", "asset_type": "crypto"},
        ],
    }

    KEY_LABELS = {
        "status": "상태",
        "message": "안내",
        "symbol": "종목",
        "asset_type": "자산",
        "price": "현재가",
        "returns": "기간 수익률",
        "volatility_annualized": "연환산 변동성",
        "as_of": "기준 시각",
        "source": "출처",
        "summaries": "시장 요약",
        "errors": "수집 오류",
        "events": "주요 일정",
        "matched": "보유자산 관련 일정",
        "news": "주요 뉴스",
        "narratives": "시장 내러티브",
        "macro": "거시 환경",
        "industry": "산업 분석",
        "analysis": "분석 결과",
        "fundamentals": "재무 분석",
        "valuation": "가치평가",
        "metrics": "핵심 지표",
        "risk_signals": "위험 신호",
        "multiples": "평가 배수",
        "timeframes": "시간대별 지표",
        "signals": "신호",
        "conflict": "신호 충돌",
        "summary": "요약",
        "performance": "성과",
        "exposure": "보유 비중",
        "grouped": "구분별 성과",
        "total_trades": "거래 수",
        "win_rate": "승률",
        "profit_factor": "Profit Factor",
        "expectancy": "거래당 기대값",
        "max_drawdown": "최대 낙폭",
        "sharpe": "Sharpe",
        "sortino": "Sortino",
        "generated_at": "생성 시각",
        "direct_trade_signal": "직접 주문 신호",
        "auto_apply": "자동 적용",
        "configuration_required": "운영 데이터 연결 필요",
    }

    def __init__(
        self,
        parent,
        dashboard_ref=None,
        mode: str = "ai_analyst",
        db_path: str = ":memory:",
        **kwargs,
    ):
        super().__init__(parent, fg_color="#0b1120", **kwargs)
        self.dashboard_ref = dashboard_ref
        self.mode = mode if mode in self.MODE_TABS else "ai_analyst"
        self.service = FinancialIntelligenceService(
            db_path=db_path,
            settings=self._financial_settings(),
        )
        self.outputs: Dict[str, ctk.CTkTextbox] = {}
        self.status_labels: Dict[str, ctk.CTkLabel] = {}
        self.chart_canvases: Dict[str, tk.Canvas] = {}
        self._cleaned_up = False
        self._async_results: queue.Queue[tuple[str, str, Any, Optional[Exception]]] = queue.Queue()
        self._async_poll_id: Optional[str] = None
        self._async_worker_count = 0
        self._async_lock = threading.Lock()
        self._build()
        try:
            self.bind("<Map>", self._on_map_visible, add="+")
        except Exception:
            pass

    def _is_visible_now(self) -> bool:
        try:
            return bool(self.winfo_exists() and self.winfo_ismapped() and self.winfo_viewable())
        except Exception:
            return False

    def _schedule_async_poll(self, delay_ms: int = 50) -> None:
        """실제 작업 또는 대기 결과가 있을 때, 보이는 탭에서만 큐를 확인한다."""
        if self._cleaned_up or self._async_poll_id is not None or not self._is_visible_now():
            return
        try:
            self._async_poll_id = self.after(delay_ms, self._poll_async_results)
        except Exception:
            self._async_poll_id = None

    def _on_map_visible(self, event=None) -> None:
        try:
            if event is not None and getattr(event, "widget", None) is not self:
                return
        except Exception:
            pass
        if not self._cleaned_up:
            self._schedule_async_poll(0)

    def _financial_settings(self) -> Dict[str, Any]:
        settings = getattr(self.dashboard_ref, "settings", {}) if self.dashboard_ref is not None else {}
        return dict((settings or {}).get("financial_intelligence", {}) or {})

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="#0f1f3d", corner_radius=12)
        header.pack(fill="x", padx=10, pady=(10, 6))
        ctk.CTkLabel(
            header,
            text="NoahAI 금융 인텔리전스",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#60a5fa",
        ).pack(anchor="w", padx=14, pady=(10, 2))
        ctk.CTkLabel(
            header,
            text=(
                "종목이나 시장을 선택하면 앱이 공개 시세와 연결된 운영 데이터를 불러옵니다. "
                "JSON 파일을 만들거나 붙여 넣을 필요가 없습니다."
            ),
            font=ctk.CTkFont(size=12),
            text_color="#cbd5e1",
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 2))
        ctk.CTkLabel(
            header,
            text="일부 뉴스·공시·기관 데이터는 운영 공급자 연결 전까지 '데이터 연결 필요'로 표시되며 임의 값을 만들지 않습니다.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            wraplength=1000,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 10))
        if self.mode == "blockchain":
            ctk.CTkLabel(
                header,
                text=(
                    "코인 정보는 내 계좌·선택 코인의 운용 상태를 보는 화면이고, "
                    "코인 탐색은 여러 코인을 조건으로 비교해 후보를 찾는 시장 검색 화면입니다."
                ),
                font=ctk.CTkFont(size=11, weight="bold"),
                text_color="#7dd3fc",
                wraplength=1000,
                justify="left",
            ).pack(anchor="w", padx=14, pady=(0, 10))

        self.tabview = ctk.CTkTabview(
            self,
            fg_color="#0b1120",
            segmented_button_fg_color="#0d223d",
            segmented_button_selected_color="#2563eb",
            segmented_button_unselected_color="#0d223d",
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        mode_accents = {
            "blockchain": "#2563eb",
            "stock": "#0f766e",
            "asset": "#6d28d9",
            "ai_analyst": "#0369a1",
        }
        style_tabview(
            self.tabview,
            accent=mode_accents.get(self.mode, "#2563eb"),
            bar_color="#0d223d",
            inactive="#1b3352",
            text_color="#e5edf6",
            font_size=11,
            height=34,
        )
        for name in self.MODE_TABS[self.mode]:
            tab = self.tabview.add(name)
            tab.configure(fg_color="#0b1120")
            self._build_tab(name, tab)

    def _build_tab(self, name: str, tab) -> None:
        builders: Dict[str, Callable] = {
            "글로벌 시장": self._build_market_tab,
            "시장·섹터": self._build_market_tab,
            "이벤트·속보": self._build_event_news_tab,
            "내러티브": self._build_narrative_tab,
            "산업·거시": self._build_macro_tab,
            "기업 분석": self._build_fundamental_tab,
            "가치평가": self._build_valuation_tab,
            "종목 탐색": self._build_screener_tab,
            "코인 탐색": self._build_screener_tab,
            "지표 탐색": self._build_technical_tab,
            "전략 검증": self._build_backtest_tab,
            "기관 동향": self._build_institutional_tab,
            "성과·위험": self._build_performance_tab,
        }
        builder = builders.get(name)
        if builder:
            builder(name, tab)

    def _panel(self, tab, title: str, description: str):
        scroll = ctk.CTkScrollableFrame(tab, fg_color="#0b1120")
        scroll.pack(fill="both", expand=True)
        card = ctk.CTkFrame(scroll, fg_color="#111827", corner_radius=12, border_width=1, border_color="#1f2937")
        card.pack(fill="x", padx=8, pady=8)
        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.pack(fill="x", padx=12, pady=(10, 0))
        ctk.CTkLabel(
            title_row,
            text=title,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#f9fafb",
        ).pack(side="left")
        ctk.CTkButton(
            title_row,
            text="AI에게 사용법 묻기",
            width=150,
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#1d4ed8",
            hover_color="#2563eb",
            command=lambda feature=title: self._ask_ai_about_feature(feature),
        ).pack(side="right")
        ctk.CTkLabel(
            card,
            text=description,
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af",
            wraplength=960,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))
        ctk.CTkLabel(
            card,
            text=f"처음 사용: {self.FEATURE_GUIDES.get(title, '입력 → 조회 → 출처와 기준시각 → 위험 표시 순으로 확인')}",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#93c5fd",
            wraplength=960,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))
        status = ctk.CTkLabel(card, text="조회 전", font=ctk.CTkFont(size=11), text_color="#93c5fd")
        status.pack(anchor="w", padx=12, pady=(0, 8))
        self.status_labels[title] = status
        return scroll, card

    def _ask_ai_about_feature(self, feature: str) -> None:
        """현재 기능의 사용법 질문을 NoahAI 어시스턴트로 전달한다."""
        dashboard = self.dashboard_ref
        prompt = (
            f"금융 인텔리전스의 '{feature}' 기능을 처음 쓰는 사용자에게 "
            "어디에 무엇을 입력하고 어떤 버튼을 누르는지, 결과를 어떤 순서로 읽는지, "
            "데이터 연결 필요 표시와 실제 주문의 관계를 NoahAI 기준으로 쉽게 설명해줘."
        )
        if feature == "종목 조건 검색" and self.mode == "blockchain":
            prompt += " 블록체인 코인 정보 화면과 코인 탐색의 차이도 함께 설명해줘."
        try:
            ensure = getattr(dashboard, "_ensure_ai_assistant_tab", None)
            if callable(ensure):
                ensure()
            assistant = getattr(dashboard, "ai_assistant_widget", None)
            if assistant is not None and hasattr(assistant, "send_quick_question"):
                if hasattr(assistant, "set_service_context"):
                    assistant.set_service_context(
                        "stock" if self.mode == "stock" else "blockchain",
                        announce=False,
                    )
                assistant.send_quick_question(prompt)
                tabview = getattr(dashboard, "tab_widget", None)
                if tabview is not None:
                    tabview.set("AI 어시스턴트")
                return
            manual = getattr(dashboard, "_open_manual_modal", None)
            if callable(manual):
                manual()
        except Exception:
            manual = getattr(dashboard, "_open_manual_modal", None)
            if callable(manual):
                manual()

    @staticmethod
    def _entry(parent, value: str = "", width: int = 180, placeholder: str = ""):
        entry = ctk.CTkEntry(parent, width=width, height=32, placeholder_text=placeholder)
        if value:
            entry.insert(0, value)
        return entry

    def _labeled_entry(self, parent, label: str, value: str, width: int = 150):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.pack(side="left", padx=(0, 8))
        ctk.CTkLabel(col, text=label, text_color="#9ca3af", font=ctk.CTkFont(size=11)).pack(anchor="w")
        entry = self._entry(col, value, width)
        entry.pack()
        return entry

    def _output(self, parent, key: str, height: int = 240, chart: bool = False):
        if chart:
            canvas = tk.Canvas(parent, height=180, bg="#07101f", highlightthickness=0)
            canvas.pack(fill="x", padx=12, pady=(8, 4))
            self.chart_canvases[key] = canvas
        box = ctk.CTkTextbox(parent, height=height, fg_color="#07101f", text_color="#dbeafe")
        box.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        box.insert("1.0", "조회 버튼을 누르면 결과가 여기에 표시됩니다.")
        box.configure(state="disabled")
        self.outputs[key] = box
        return box

    def _show(self, key: str, value: Any, status_key: Optional[str] = None, status: str = "완료") -> None:
        box = self.outputs.get(key)
        if box is not None:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("1.0", self._format_result(value))
            box.configure(state="disabled")
        chart_points = value.get("_chart_points") if isinstance(value, dict) else None
        if chart_points and key in self.chart_canvases:
            self._draw_chart(self.chart_canvases[key], chart_points)
        if status_key and status_key in self.status_labels:
            status_text = status
            if isinstance(value, dict) and value.get("status") == "configuration_required":
                status_text = "운영 데이터 연결 필요"
            self.status_labels[status_key].configure(
                text=status_text,
                text_color="#22c55e" if status_text == "완료" else "#f59e0b",
            )

    def _error(self, key: str, title: str, exc: Exception) -> None:
        self._show(
            key,
            {"status": "error", "message": f"입력값 또는 데이터 연결을 확인하세요. ({type(exc).__name__})"},
            title,
            "확인 필요",
        )

    def _format_result(self, value: Any) -> str:
        if isinstance(value, dict) and value.get("status") == "configuration_required":
            return str(value.get("message") or "이 기능은 운영 데이터 공급자 연결 후 자동으로 제공됩니다.")
        lines: List[str] = []
        self._append_lines(lines, value)
        return "\n".join(lines).strip() or "표시할 데이터가 없습니다."

    def _append_lines(self, lines: List[str], value: Any, depth: int = 0, key: str = "") -> None:
        indent = "  " * depth
        if isinstance(value, dict):
            for raw_key, item in value.items():
                if str(raw_key).startswith("_"):
                    continue
                label = self.KEY_LABELS.get(str(raw_key), str(raw_key).replace("_", " "))
                if isinstance(item, (dict, list)):
                    lines.append(f"{indent}{label}")
                    self._append_lines(lines, item, depth + 1, str(raw_key))
                else:
                    lines.append(f"{indent}{label}: {self._format_scalar(item, str(raw_key))}")
        elif isinstance(value, list):
            if not value:
                lines.append(f"{indent}데이터 없음")
            for index, item in enumerate(value, start=1):
                if isinstance(item, dict):
                    symbol = item.get("symbol") or item.get("title") or item.get("name")
                    lines.append(f"{indent}{index}. {symbol or ''}".rstrip())
                    self._append_lines(lines, item, depth + 1, key)
                else:
                    lines.append(f"{indent}- {self._format_scalar(item, key)}")
        else:
            lines.append(f"{indent}{self._format_scalar(value, key)}")

    @staticmethod
    def _format_scalar(value: Any, key: str = "") -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "예" if value else "아니오"
        if isinstance(value, float):
            if "rate" in key or "percent" in key or "return" in key or "volatility" in key:
                return f"{value:,.2f}%"
            return f"{value:,.4f}".rstrip("0").rstrip(".")
        return str(value)

    @staticmethod
    def _draw_chart(canvas: tk.Canvas, points: Iterable[Any]) -> None:
        values: List[float] = []
        for point in points:
            try:
                if isinstance(point, dict):
                    values.append(float(point.get("price", point.get("close"))))
                else:
                    values.append(float(point))
            except Exception:
                continue
        canvas.delete("all")
        if len(values) < 2:
            canvas.create_text(12, 14, anchor="nw", text="차트 데이터가 부족합니다.", fill="#94a3b8")
            return
        width = max(400, canvas.winfo_width() or 900)
        height = max(160, canvas.winfo_height() or 180)
        low, high = min(values), max(values)
        span = high - low or 1.0
        coords: List[float] = []
        for index, value in enumerate(values):
            x = 12 + (width - 24) * index / max(1, len(values) - 1)
            y = 12 + (height - 34) * (high - value) / span
            coords.extend([x, y])
        canvas.create_line(*coords, fill="#60a5fa", width=2, smooth=True)
        canvas.create_text(12, height - 8, anchor="sw", text=f"최저 {low:,.2f}", fill="#94a3b8")
        canvas.create_text(width - 12, height - 8, anchor="se", text=f"최고 {high:,.2f}", fill="#94a3b8")

    def _run_async(self, title: str, task: Callable[[], Any], output_key: str) -> None:
        if title in self.status_labels:
            self.status_labels[title].configure(text="수집·계산 중", text_color="#fbbf24")
        with self._async_lock:
            self._async_worker_count += 1
        self._schedule_async_poll(50)

        def worker():
            try:
                result = task()
                if not self._cleaned_up:
                    self._async_results.put((title, output_key, result, None))
            except Exception as exc:
                if not self._cleaned_up:
                    self._async_results.put((title, output_key, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _prepare_async(self, title: str, prepare: Callable[[], Callable[[], Any]], output_key: str) -> None:
        try:
            task = prepare()
        except Exception as exc:
            self._error(output_key, title, exc)
            return
        self._run_async(title, task, output_key)

    def _poll_async_results(self) -> None:
        self._async_poll_id = None
        if self._cleaned_up:
            return
        completed = 0
        try:
            while True:
                title, output_key, result, error = self._async_results.get_nowait()
                completed += 1
                if error is None:
                    self._show(output_key, result, title)
                else:
                    self._error(output_key, title, error)
        except queue.Empty:
            pass
        if completed:
            with self._async_lock:
                self._async_worker_count = max(0, self._async_worker_count - completed)
        with self._async_lock:
            workers_active = self._async_worker_count > 0
        if workers_active or not self._async_results.empty():
            self._schedule_async_poll(100)

    def _fetch_market_rows(self, universe: List[Dict[str, str]]) -> Dict[str, Any]:
        hydrated: List[Dict[str, Any]] = []
        chart_points: List[Dict[str, Any]] = []
        for item in universe:
            symbol = item["symbol"]
            asset_type = item["asset_type"]
            fetched = (
                self.service.provider.fetch_binance_history(symbol)
                if asset_type == "crypto"
                else self.service.provider.fetch_yahoo_history(symbol, asset_type=asset_type)
            )
            points = list(fetched.get("points") or [])
            hydrated.append({**item, "points": points})
            if not chart_points and points:
                chart_points = points
        result = self.service.global_market(hydrated, use_network=False)
        result["_chart_points"] = chart_points
        return result

    def _build_market_tab(self, name: str, tab) -> None:
        title = "시장 현황과 수익률"
        _, card = self._panel(
            tab,
            title,
            "주요 지수·종목·환율·원자재·가상자산의 가격, 기간 수익률, 변동성과 출처를 차트와 함께 확인합니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        default_preset = "가상자산" if self.mode == "blockchain" else "주요 시장"
        preset = ctk.StringVar(value=default_preset)
        ctk.CTkOptionMenu(row, variable=preset, values=list(self.MARKET_PRESETS) + ["직접 입력"], width=130).pack(side="left", padx=(0, 8))
        symbols = self._entry(row, "", 360, "예: 삼성전자 005930.KS, Apple AAPL, BTC")
        symbols.pack(side="left", padx=(0, 8))
        asset = ctk.StringVar(value="crypto" if self.mode == "blockchain" else "stock")
        ctk.CTkOptionMenu(row, variable=asset, values=["stock", "etf", "index", "fx", "commodity", "crypto"], width=110).pack(side="left", padx=(0, 8))

        def prepare_market():
            selected = preset.get()
            if selected == "직접 입력":
                universe = [
                    {"symbol": token.strip(), "asset_type": asset.get()}
                    for token in symbols.get().split(",")
                    if token.strip()
                ]
                if not universe:
                    raise ValueError("종목을 한 개 이상 입력하세요")
            else:
                universe = [dict(row) for row in self.MARKET_PRESETS[selected]]
            return lambda: self._fetch_market_rows(universe)

        ctk.CTkButton(row, text="시장 현황 조회", command=lambda: self._prepare_async(title, prepare_market, name)).pack(side="left")
        self._output(card, name, 250, chart=True)

    def _configured_events(self) -> List[Dict[str, Any]]:
        return [dict(row) for row in self._financial_settings().get("event_feed_items", []) if isinstance(row, dict)]

    def _configured_rss_urls(self) -> List[str]:
        return [str(url).strip() for url in self._financial_settings().get("news_rss_urls", []) if str(url).strip()]

    def _build_event_news_tab(self, name: str, tab) -> None:
        title = "보유자산 일정과 속보"
        _, card = self._panel(
            tab,
            title,
            "연결된 일정·뉴스 공급자에서 보유자산과 관련된 항목을 우선 표시합니다. 사용자가 JSON이나 RSS 주소를 입력하지 않습니다.",
        )

        def prepare_events():
            positions = self._dashboard_positions()
            events = self._configured_events()
            rss_urls = self._configured_rss_urls()

            def task():
                if not events and not rss_urls:
                    return {
                        "status": "configuration_required",
                        "message": "현재 운영 일정·뉴스 공급자가 연결되지 않았습니다. 공개 시세 기능은 사용할 수 있으며, 뉴스·일정은 중앙 공급자 연결 후 자동 제공됩니다.",
                    }
                result = self.service.event_risk(events, positions)
                news_rows: List[Dict[str, Any]] = []
                for url in rss_urls:
                    news_rows.extend(self.service.news.fetch_rss(url).get("items") or [])
                if news_rows:
                    result["news"] = self.service.news_and_narratives(news_rows, self._held_symbols())
                return result

            return task

        ctk.CTkButton(card, text="일정·속보 확인", command=lambda: self._prepare_async(title, prepare_events, name)).pack(anchor="w", padx=12, pady=4)
        self._output(card, name, 360)

    def _build_narrative_tab(self, name: str, tab) -> None:
        title = "시장 내러티브"
        _, card = self._panel(
            tab,
            title,
            "연결된 뉴스에서 반복 기사를 제거하고 보유자산·주제·파급력 기준으로 시장의 주요 이야기를 정리합니다.",
        )

        def prepare_narrative():
            rss_urls = self._configured_rss_urls()

            def task():
                if not rss_urls:
                    return {
                        "status": "configuration_required",
                        "message": "운영 뉴스 공급자가 연결되지 않았습니다. 중앙 뉴스 피드 또는 허가된 RSS가 연결되면 이 화면이 자동으로 채워집니다.",
                    }
                rows: List[Dict[str, Any]] = []
                for url in rss_urls:
                    rows.extend(self.service.news.fetch_rss(url).get("items") or [])
                return self.service.news_and_narratives(rows, self._held_symbols())

            return task

        ctk.CTkButton(card, text="내러티브 확인", command=lambda: self._prepare_async(title, prepare_narrative, name)).pack(anchor="w", padx=12, pady=4)
        self._output(card, name, 380)

    def _build_macro_tab(self, name: str, tab) -> None:
        title = "산업·거시경제"
        _, card = self._panel(
            tab,
            title,
            "성장·물가·유동성·신용·금리 데이터 공급자가 연결되면 현재 경기 국면과 자산군 영향을 자동으로 설명합니다.",
        )

        def prepare_macro():
            indicators = self._financial_settings().get("macro_indicators")
            return lambda: (
                {"macro": self.service.macro.classify(indicators)}
                if isinstance(indicators, dict) and indicators
                else {
                    "status": "configuration_required",
                    "message": "공식 거시지표 공급자가 아직 연결되지 않았습니다. 임의 수치를 입력받아 결과를 만드는 대신 연결 전 상태를 정확히 표시합니다.",
                }
            )

        ctk.CTkButton(card, text="거시 환경 확인", command=lambda: self._prepare_async(title, prepare_macro, name)).pack(anchor="w", padx=12, pady=4)
        self._output(card, name, 360)

    def _build_fundamental_tab(self, name: str, tab) -> None:
        title = "기업 재무분석"
        _, card = self._panel(
            tab,
            title,
            "종목 식별값만 입력하면 설정된 공시 공급자에서 재무 데이터를 가져옵니다. API 키나 원본 JSON은 운영 설정에서 관리합니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        provider = ctk.StringVar(value="DART")
        ctk.CTkOptionMenu(row, variable=provider, values=["DART", "SEC"], width=100).pack(side="left", padx=(0, 8))
        code = self._entry(row, "", 220, "DART 기업코드 또는 SEC CIK")
        code.pack(side="left", padx=(0, 8))
        year = self._entry(row, "2025", 90)
        year.pack(side="left", padx=(0, 8))

        def prepare_regulatory():
            provider_name = provider.get()
            code_value = code.get().strip()
            year_value = year.get().strip()
            if not code_value:
                raise ValueError("기업 식별값을 입력하세요")
            settings = self._financial_settings()
            if provider_name == "SEC":
                user_agent = str(settings.get("sec_user_agent") or "")
                return lambda: self.service.fetch_stock_research("sec", cik=code_value, sec_user_agent=user_agent)
            api_key = str(settings.get("dart_api_key") or "")
            return lambda: self.service.fetch_stock_research(
                "dart",
                corp_code=code_value,
                business_year=year_value,
                dart_api_key=api_key,
            )

        ctk.CTkButton(row, text="공시 재무 분석", command=lambda: self._prepare_async(title, prepare_regulatory, name)).pack(side="left")
        self._output(card, name, 380)

    def _build_valuation_tab(self, name: str, tab) -> None:
        title = "기업 가치평가"
        _, card = self._panel(
            tab,
            title,
            "현금흐름과 주식 수를 이용해 보수·기준·낙관 시나리오 범위를 계산합니다. 목표가격이나 수익을 보장하지 않습니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=6)
        base_fcf = self._labeled_entry(row, "기준 잉여현금흐름", "10000000000", 180)
        shares = self._labeled_entry(row, "발행주식 수", "100000000", 160)
        net_debt = self._labeled_entry(row, "순부채", "0", 150)

        def prepare_valuation():
            values = (float(base_fcf.get()), float(shares.get()), float(net_debt.get()))
            return lambda: self.service.valuation.scenario_dcf(*values)

        ctk.CTkButton(row, text="시나리오 계산", command=lambda: self._prepare_async(title, prepare_valuation, name)).pack(side="left", padx=8, pady=(18, 0))
        self._output(card, name, 360)

    def _build_screener_tab(self, name: str, tab) -> None:
        title = "종목 조건 검색"
        _, card = self._panel(
            tab,
            title,
            "관심 종목을 입력하고 최소 가격을 선택하면 공개 시세 기준으로 조건에 맞는 종목을 정리합니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        default_symbols = "BTC,ETH,SOL" if self.mode == "blockchain" else "AAPL,MSFT,005930.KS,000660.KS"
        symbols = self._entry(row, default_symbols, 380)
        symbols.pack(side="left", padx=(0, 8))
        min_price = self._labeled_entry(row, "최소 가격", "0", 100)
        asset_type = "crypto" if self.mode == "blockchain" else "stock"

        def prepare_screener():
            universe = [{"symbol": token.strip(), "asset_type": asset_type} for token in symbols.get().split(",") if token.strip()]
            threshold = float(min_price.get() or 0)

            def task():
                market = self._fetch_market_rows(universe)
                rows = list(market.get("summaries") or [])
                screened = self.service.screener.screen(rows, [{"field": "price", "op": "gte", "value": threshold}])
                return {"status": market.get("status"), "조건 통과 종목": screened, "수집 오류": market.get("errors") or []}

            return task

        ctk.CTkButton(row, text="조건 검색", command=lambda: self._prepare_async(title, prepare_screener, name)).pack(side="left", padx=8, pady=(18, 0))
        self._output(card, name, 340)

    def _fetch_symbol_history(self, symbol: str, asset_type: str, interval: str = "1d") -> Dict[str, Any]:
        if asset_type == "crypto":
            return self.service.provider.fetch_binance_history(symbol, interval=interval, limit=200)
        return self.service.provider.fetch_yahoo_history(symbol, range_name="6mo", interval=interval, asset_type=asset_type)

    def _build_technical_tab(self, name: str, tab) -> None:
        title = "기술지표"
        _, card = self._panel(
            tab,
            title,
            "종목을 선택하면 가격 차트와 RSI·MACD·이동평균·볼린저밴드를 자동 계산합니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        crypto = self.mode == "blockchain"
        symbol = self._entry(row, "BTC" if crypto else "AAPL", 220)
        symbol.pack(side="left", padx=(0, 8))
        asset_type = "crypto" if crypto else "stock"

        def prepare_technical():
            symbol_value = symbol.get().strip()
            if not symbol_value:
                raise ValueError("종목을 입력하세요")

            def task():
                fetched = self._fetch_symbol_history(symbol_value, asset_type)
                points = list(fetched.get("points") or [])
                closes = [point.get("close", point.get("price")) for point in points]
                volumes = [point.get("volume", 0) for point in points]
                result = self.service.technical.analyze(closes, volumes)
                return {"종목": symbol_value.upper(), **result, "_chart_points": points}

            return task

        ctk.CTkButton(row, text="지표 조회", command=lambda: self._prepare_async(title, prepare_technical, name)).pack(side="left")
        self._output(card, name, 300, chart=True)

    def _build_backtest_tab(self, name: str, tab) -> None:
        title = "전략 검증"
        _, card = self._panel(
            tab,
            title,
            "종목과 이동평균 기간을 선택하면 공개 과거 시세에 수수료·슬리피지·다음 봉 체결을 반영해 검증합니다.",
        )
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        crypto = self.mode == "blockchain"
        symbol = self._labeled_entry(row, "종목", "BTC" if crypto else "AAPL", 180)
        fast = self._labeled_entry(row, "빠른 평균", "5", 90)
        slow = self._labeled_entry(row, "느린 평균", "20", 90)
        asset_type = "crypto" if crypto else "stock"

        def prepare_backtest():
            symbol_value = symbol.get().strip()
            fast_n, slow_n = int(fast.get()), int(slow.get())
            if fast_n <= 0 or slow_n <= fast_n:
                raise ValueError("느린 평균은 빠른 평균보다 커야 합니다")

            def task():
                fetched = self._fetch_symbol_history(symbol_value, asset_type)
                points = list(fetched.get("points") or [])
                bars = [{"open": row.get("open"), "close": row.get("close", row.get("price"))} for row in points]

                def signal(rows, index):
                    if index < slow_n:
                        return "HOLD"
                    closes = [float(row.get("close")) for row in rows[: index + 1] if row.get("close") is not None]
                    if len(closes) < slow_n:
                        return "HOLD"
                    return "LONG" if sum(closes[-fast_n:]) / fast_n > sum(closes[-slow_n:]) / slow_n else "CLOSE"

                result = self.service.backtest.run(
                    bars,
                    signal,
                    fee_rate=0.001,
                    slippage_bps=5,
                    spread_bps=2,
                    execution_delay_bars=1,
                ).to_dict()
                return {**result, "_chart_points": points}

            return task

        ctk.CTkButton(row, text="전략 검증 실행", command=lambda: self._prepare_async(title, prepare_backtest, name)).pack(side="left", padx=8, pady=(18, 0))
        self._output(card, name, 360, chart=True)

    def _build_institutional_tab(self, name: str, tab) -> None:
        title = "기관 보유 변화"
        _, card = self._panel(
            tab,
            title,
            "허가된 기관 공시 공급자가 연결되면 신규 편입·비중 확대·축소와 공통 보유종목을 표시합니다.",
        )

        def prepare_institutional():
            settings = self._financial_settings()
            current = settings.get("institutional_current")
            previous = settings.get("institutional_previous")
            return lambda: (
                self.service.institutional.changes(current, previous)
                if isinstance(current, list) and isinstance(previous, list)
                else {
                    "status": "configuration_required",
                    "message": "기관 보유 데이터 공급자가 아직 연결되지 않았습니다. 공시 지연과 이용권한을 확인한 데이터만 제공할 예정입니다.",
                }
            )

        ctk.CTkButton(card, text="기관 동향 확인", command=lambda: self._prepare_async(title, prepare_institutional, name)).pack(anchor="w", padx=12, pady=4)
        self._output(card, name, 360)

    def _build_performance_tab(self, name: str, tab) -> None:
        title = "내 계좌 성과·위험"
        _, card = self._panel(
            tab,
            title,
            "현재 대시보드의 보유자산과 거래 기록을 자동으로 읽어 수수료 차감 성과, 최대 낙폭과 집중도를 계산합니다.",
        )

        def prepare_performance():
            positions = self._dashboard_positions()
            trades = self._dashboard_trades()
            return lambda: (
                self.service.portfolio_report(positions, trades)
                if positions or trades
                else {
                    "status": "no_data",
                    "message": "연결된 계좌의 보유자산이나 종료 거래 기록이 없습니다.",
                }
            )

        ctk.CTkButton(card, text="내 성과 분석", command=lambda: self._prepare_async(title, prepare_performance, name)).pack(anchor="w", padx=12, pady=4)
        self._output(card, name, 420)

    def _dashboard_positions(self) -> List[Dict[str, Any]]:
        dashboard = self.dashboard_ref
        candidates: List[Any] = []
        for attr in ("current_positions", "positions", "all_positions"):
            value = getattr(dashboard, attr, None) if dashboard is not None else None
            if isinstance(value, list):
                candidates.extend(value)
            elif isinstance(value, dict):
                candidates.extend(value.values())
        return self._normalize_rows(candidates)

    def _dashboard_trades(self) -> List[Dict[str, Any]]:
        dashboard = self.dashboard_ref
        candidates: List[Any] = []
        for attr in ("recent_trades", "trades", "trade_history", "closed_trades"):
            value = getattr(dashboard, attr, None) if dashboard is not None else None
            if isinstance(value, list):
                candidates.extend(value)
            elif isinstance(value, dict):
                candidates.extend(value.values())
        return self._normalize_rows(candidates)

    @staticmethod
    def _normalize_rows(values: Iterable[Any]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for value in values:
            if isinstance(value, dict):
                normalized.append(dict(value))
            elif hasattr(value, "__dict__"):
                normalized.append(dict(value.__dict__))
        return normalized

    def _held_symbols(self) -> List[str]:
        return [
            str(row.get("symbol") or row.get("code") or "").upper()
            for row in self._dashboard_positions()
            if row.get("symbol") or row.get("code")
        ]

    def cleanup(self) -> None:
        self._cleaned_up = True
        if self._async_poll_id is not None:
            try:
                self.after_cancel(self._async_poll_id)
            except Exception:
                pass
            self._async_poll_id = None
        with self._async_lock:
            self._async_worker_count = 0
        try:
            self.service.store.close()
        except Exception:
            pass

    def destroy(self) -> None:
        self.cleanup()
        super().destroy()
