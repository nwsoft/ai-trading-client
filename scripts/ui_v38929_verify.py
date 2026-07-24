#!/usr/bin/env python3
"""v3.9.0.0 UI를 실계정/네트워크 없이 렌더링하는 개발 검증 화면."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import customtkinter as ctk

from ui.dashboard_modern import ModernDashboard
from ui.widgets.custom_strategy_widget import CustomStrategyWidget
from ui.widgets.user_manual_widget import UserManualWidget


class StatsHarness(ctk.CTkFrame):
    create_exchange_balance_section = ModernDashboard.create_exchange_balance_section
    create_exchange_positions_section = ModernDashboard.create_exchange_positions_section
    create_exchange_stats_section = ModernDashboard.create_exchange_stats_section
    create_broker_stats_section = ModernDashboard.create_broker_stats_section
    _format_balance_number = ModernDashboard._format_balance_number
    _balance_metric_items = ModernDashboard._balance_metric_items
    _update_balance_metric_widgets = ModernDashboard._update_balance_metric_widgets
    _position_value = staticmethod(ModernDashboard._position_value)
    _format_position_number = ModernDashboard._format_position_number
    _render_position_cards = ModernDashboard._render_position_cards

    def __init__(self, master):
        super().__init__(master, fg_color="#0b1120")
        self.exchange_section_widgets = {}
        self.broker_section_widgets = {}
        self.stock_adapters = {}
        class FakeClient:
            @staticmethod
            def futures_position_information():
                return [
                    {"symbol": "BTCUSDT", "positionAmt": "0.018", "entryPrice": "64210.4", "unRealizedProfit": "34.72", "leverage": "3"},
                    {"symbol": "ETHUSDT", "positionAmt": "-0.42", "entryPrice": "3188.7", "unRealizedProfit": "-8.16", "leverage": "2"},
                    {"symbol": "SOLUSDT", "positionAmt": "7.5", "entryPrice": "171.25", "unRealizedProfit": "12.48", "leverage": "2"},
                ]

        class FakeTrader:
            binance_client = type("BinanceClientWrapper", (), {"client": FakeClient()})()
            active_positions = {}

        class FakeMainApp:
            trader = FakeTrader()

        class FakeUnifiedManager:
            @staticmethod
            def get_exchange_balance(_exchange, _trading_type):
                return {"status": "success", "balance": {"USDT": 12480.62, "BTC": 0.0842, "ETH": 1.725}}

        self.main_app = FakeMainApp()
        self.unified_manager = FakeUnifiedManager()
        self.unified_trader = None
        self.logger = __import__("logging").getLogger("ui_verify")

    @staticmethod
    def _get_safe_font(kind, fallback=None):
        sizes = {"title": (15, "bold"), "small": (11, "normal"), "body": (13, "normal")}
        size, weight = sizes.get(kind, (13, "normal"))
        return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)

    @staticmethod
    def _color(_name, fallback):
        return fallback

    @staticmethod
    def _get_dashboard_read_db_path():
        return str(ROOT / "data" / "ui-verify-no-db.sqlite")

    def thread_safe_after(self, delay, callback):
        # 첫 렌더만 수행하고 반복 갱신 예약은 만들지 않는다.
        if delay <= 250:
            return self.after(delay, callback)
        return None

    @staticmethod
    def _get_stock_adapter(_broker):
        return None


def main():
    ctk.set_appearance_mode("dark")
    root = ctk.CTk()
    root.title("NoahAI v3.9.0.0 UI Verification")
    root.geometry("1280x820")
    root.lift()
    root.attributes("-topmost", True)
    root.after(1200, lambda: root.attributes("-topmost", False))

    tabs = ctk.CTkTabview(root, fg_color="#0b1120")
    tabs.pack(fill="both", expand=True, padx=10, pady=10)

    stats_tab = tabs.add("거래소 요약")
    harness = StatsHarness(stats_tab)
    harness.pack(fill="both", expand=True, padx=14, pady=14)
    ctk.CTkLabel(
        harness, text="BINANCE 탭 · 잔고 / 멀티 포지션 / 거래통계 실제 컴포넌트",
        font=ctk.CTkFont(size=22, weight="bold"), text_color="#f8fafc",
    ).pack(anchor="w", padx=10, pady=(10, 12))

    row = ctk.CTkFrame(harness, fg_color="transparent")
    row.pack(fill="both", expand=True, padx=8)
    left = ctk.CTkFrame(row, width=500, fg_color="transparent")
    left.pack(side="left", fill="y", padx=(0, 10))
    left.pack_propagate(False)

    balance = ctk.CTkFrame(left, height=96, fg_color="#18212f", corner_radius=14, border_width=1, border_color="#334155")
    balance.pack(fill="x", pady=(0, 8))
    balance.pack_propagate(False)
    harness.create_exchange_balance_section(balance, "binance")

    positions = ctk.CTkFrame(left, height=260, fg_color="#18212f", corner_radius=14, border_width=1, border_color="#334155")
    positions.pack(fill="x", pady=(0, 8))
    positions.pack_propagate(False)
    harness.create_exchange_positions_section(positions, "binance")

    exchange = ctk.CTkFrame(left, height=88, fg_color="#18212f", corner_radius=14, border_width=1, border_color="#334155")
    exchange.pack(fill="x")
    exchange.pack_propagate(False)
    harness.create_exchange_stats_section(exchange, "binance")

    log_preview = ctk.CTkFrame(row, fg_color="#111827", corner_radius=14, border_width=1, border_color="#334155")
    log_preview.pack(side="left", fill="both", expand=True)
    ctk.CTkLabel(
        log_preview, text="실시간 거래 로그 영역", font=ctk.CTkFont(size=17, weight="bold"), text_color="#cbd5e1",
    ).pack(anchor="w", padx=18, pady=(18, 8))
    ctk.CTkLabel(
        log_preview,
        text="포지션 3개가 좌측 카드 안에 동시에 표시되고\n4번째부터는 포지션 영역 내부에서 스크롤됩니다.\n\n거래 통계는 88px 슬림 KPI 바로 유지되어\n오른쪽 로그 공간이나 포지션 공간을 침범하지 않습니다.",
        justify="left", font=ctk.CTkFont(size=15), text_color="#94a3b8",
    ).pack(anchor="w", padx=18, pady=8)

    ctk.CTkLabel(
        harness,
        text="실제 앱: 왼쪽 패널 500~620px · 포지션 최소 230px · 거래통계 88px · 초과 포지션 내부 스크롤",
        font=ctk.CTkFont(size=13), text_color="#94a3b8",
    ).pack(anchor="w", padx=10, pady=(10, 14))

    custom_tab = tabs.add("AI 커스텀")
    custom = CustomStrategyWidget(custom_tab, dashboard=None, settings={})
    custom.pack(fill="both", expand=True)

    tabs.set("AI 커스텀" if "--custom" in sys.argv else "거래소 요약")
    if "--manual" in sys.argv:
        root.manual_widget = UserManualWidget(root)
        root.after(250, lambda: root.manual_widget.show_manual("🧠 AI 커스텀"))
    root.mainloop()


if __name__ == "__main__":
    main()
