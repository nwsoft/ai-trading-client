from datetime import datetime
from pathlib import Path
import subprocess
import sys

import pytest

from config.settings import normalize_trade_rate
from trading.ai.auto_optimizer import AIAutoOptimizer
from trading.optimizer import Optimizer


ROOT = Path(__file__).resolve().parents[1]


class _Recorder:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.query = ""

    def execute_query(self, query, params=()):
        self.query = query
        return list(self.rows)


def test_auto_optimizer_proposes_without_mutating_shared_settings():
    settings = {
        "default_tp": 0.0018,
        "default_sl": 0.0020,
        "default_leverage": 5,
    }
    optimizer = AIAutoOptimizer(None, _Recorder(), settings)
    stats = {"win_rate": 0.2, "avg_profit_percent": -0.01, "max_drawdown": -0.03}

    first = optimizer._maybe_adjust_parameters(stats)
    second = optimizer._maybe_adjust_parameters(stats)

    assert settings == {
        "default_tp": 0.0018,
        "default_sl": 0.0020,
        "default_leverage": 5,
    }
    assert first["requires_approval"] is True
    assert first["default_tp"] == pytest.approx(0.00198)
    assert second["default_tp"] == pytest.approx(first["default_tp"])


def test_price_like_tp_is_rejected_to_safe_fraction():
    assert normalize_trade_rate(8307.968009445398, kind="tp") == (0.0018, True)
    assert normalize_trade_rate(0.18, kind="tp") == (0.0018, True)
    assert normalize_trade_rate(1.0, kind="sl") == (0.01, True)


def test_optimizer_reads_explicit_trade_columns_in_correct_order():
    recorder = _Recorder([
        (
            "BTCUSDT", 100.0, 101.0, 0.5, 2, 0.5, 1.0,
            "2026-07-24T10:00:00", "2026-07-24T10:15:00", "TP",
        )
    ])
    optimizer = Optimizer(recorder, settings={"default_tp": 0.0018, "default_sl": 0.002})

    rows = optimizer.get_recent_trades("BTCUSDT")

    assert "SELECT symbol, entry_price, exit_price" in recorder.query
    assert rows[0]["symbol"] == "BTCUSDT"
    assert rows[0]["entry_price"] == 100.0
    assert rows[0]["pnl_percent"] == 1.0
    assert rows[0]["entry_time"] == datetime(2026, 7, 24, 10, 0)


def test_optimizer_converts_pnl_percent_points_to_fraction_and_caps_output():
    optimizer = Optimizer(_Recorder(), settings={"default_tp": 0.0018, "default_sl": 0.002})
    result = optimizer.optimize_tp_sl([
        {"pnl": 1.0, "pnl_percent": 0.5},
        {"pnl": 2.0, "pnl_percent": 1.0},
        {"pnl": -1.0, "pnl_percent": -0.4},
    ])

    assert 0.0005 <= result["optimal_tp_ratio"] <= 0.05
    assert result["optimal_tp_ratio"] == pytest.approx(0.008)
    assert result["optimal_sl_ratio"] == pytest.approx(0.0044)


def test_corrupted_existing_setting_cannot_be_reused_as_validation_fallback():
    optimizer = Optimizer(
        _Recorder(),
        settings={"default_tp": 8307.968009445398, "default_sl": 9000},
    )
    optimizer.update_settings({"default_tp": 9999, "default_sl": 9999})

    assert optimizer.settings["default_tp"] == pytest.approx(0.0018)
    assert optimizer.settings["default_sl"] == pytest.approx(0.0020)
    empty_result = optimizer.optimize_tp_sl([])
    assert empty_result["optimal_tp_ratio"] == pytest.approx(0.0018)
    assert empty_result["optimal_sl_ratio"] == pytest.approx(0.0020)


def test_coin_and_stock_info_tabs_scroll_as_whole_and_show_user_activity():
    source = (ROOT / "ui" / "dashboard_modern.py").read_text(encoding="utf-8")
    coin_section = source.split("def _ensure_coin_info_tab", 1)[1].split(
        "def _search_coin_symbol", 1
    )[0]
    stock_section = source.split("def _ensure_stock_info_tab", 1)[1].split(
        "def _search_stock_symbol", 1
    )[0]
    assert "main_container = ctk.CTkScrollableFrame(" in coin_section
    assert "main_container = ctk.CTkScrollableFrame(" in stock_section
    assert 'label_text="내 보유·최근 체결 종목"' in source
    assert 'label_text=f"시장 종목 미리보기 · 검색용' in source
    assert "def _collect_stock_user_activity" in source
    assert 'self.evaluator_scroll.pack(fill="x"' in source
    assert 'self.stock_search_results.pack(fill="x"' in source
    assert 'self.stock_evaluator_scroll.pack(fill="x"' in source


def test_stock_user_activity_prefers_holding_and_keeps_recent_trade_symbol():
    # 다른 UI 테스트가 customtkinter 모듈을 교체하므로 깨끗한 프로세스에서 검증한다.
    script = r'''
from ui.dashboard_modern import ModernDashboard
class Adapter:
    def get_positions(self):
        return [{"code": "005930", "name": "삼성전자", "quantity": 10,
                 "current_price": 72000, "pnl": 20000}]
    def get_trade_history(self, limit=100):
        return [
            {"symbol": "005930", "side": "BUY", "quantity": 10, "price": 70000},
            {"symbol": "000660", "side": "SELL", "quantity": 2, "price": 180000},
        ]
rows = ModernDashboard._collect_stock_user_activity(None, "mock", Adapter())
assert [row["code"] for row in rows] == ["005930", "000660"], rows
assert rows[0]["status"] == "보유", rows
assert rows[1]["status"] == "최근 체결", rows
assert rows[1]["detail"] == "매도", rows
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
