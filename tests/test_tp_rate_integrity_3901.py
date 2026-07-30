from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from ai_chat_strategy import AITradingChatbot
from config.settings import load_settings, normalize_trade_rate
from trading.ai.auto_optimizer import AIAutoOptimizer
from trading.optimizer import Optimizer
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


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
    assistant_source = (
        ROOT / "ui" / "widgets" / "ai_assistant_widget.py"
    ).read_text(encoding="utf-8")
    assert "settings.get('default_tp', 0.18)" not in assistant_source
    assert "settings.get('default_sl', 0.20)" not in assistant_source
    assert "settings.get('default_sl', 0.10)" not in assistant_source
    trader_source = (ROOT / "trading" / "trader.py").read_text(encoding="utf-8")
    assert "enhanced_params.get('tp_percent', 0.18)" not in trader_source
    assert "enhanced_params.get('sl_percent', 0.20)" not in trader_source
    assert "✅ TP/SL 설정 정규화 완료" not in trader_source
    assert "✅ TP/SL 설정 확인 완료 (주문 단위 fraction)" in trader_source


def test_legacy_percent_tp_sl_is_persisted_once_on_settings_load(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "settings.json"
    config_path.write_text(
        json.dumps(
            {
                "version": "3.9.0.3",
                "default_tp": 0.18,
                "default_sl": 0.2,
                "_ai_custom_runtime_safe_default_v3900_applied": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    first = load_settings()
    persisted_after_first = json.loads(config_path.read_text(encoding="utf-8"))
    second = load_settings()
    persisted_after_second = json.loads(config_path.read_text(encoding="utf-8"))

    assert first["default_tp"] == pytest.approx(0.0018)
    assert first["default_sl"] == pytest.approx(0.0020)
    assert second["default_tp"] == pytest.approx(0.0018)
    assert second["default_sl"] == pytest.approx(0.0020)
    assert persisted_after_first["default_tp"] == pytest.approx(0.0018)
    assert persisted_after_first["default_sl"] == pytest.approx(0.0020)
    assert persisted_after_second == persisted_after_first


def test_runtime_strategy_preset_converts_percent_points_before_trader_update():
    class _Trader:
        def __init__(self):
            self.settings = {
                "default_leverage": 1,
                "default_tp": 0.0018,
                "default_sl": 0.0020,
            }
            self.updates = []

        def update_settings(self, values):
            self.updates.append(dict(values))
            self.settings.update(values)

    trader = _Trader()
    chatbot = AITradingChatbot(None, trader, None)

    balanced = chatbot.strategy_presets["balanced"].parameters
    assert balanced["_unit"] == "percent_points"
    assert chatbot.apply_strategy_changes({
        "type": "strategy_change",
        "parameters": balanced,
    })

    assert trader.updates == [{
        "default_leverage": 1,
        "default_tp": pytest.approx(0.0018),
        "default_sl": pytest.approx(0.0020),
    }]


def test_unified_trader_defensively_normalizes_legacy_tp_sl_for_all_exchanges():
    class _Logger:
        def info(self, _message):
            pass

        def warning(self, _message):
            pass

    trader = object.__new__(UnifiedTrader)
    trader.settings = {"default_tp": 0.0018, "default_sl": 0.0020}
    trader.logger = _Logger()
    trader.enabled_exchanges = []
    trader.trade_enabled_exchanges = []
    trader.learning_enabled_exchanges = []
    trader._compute_enabled_exchanges = lambda: []
    trader._compute_trade_enabled_exchanges = lambda: []
    trader._compute_learning_enabled_exchanges = lambda: []
    trader.trade_stats = {}
    trader.paper_trade_stats = {}
    trader.active_positions = {}
    trader.paper_positions = {}
    trader.monitoring_flags = {}
    trader.monitoring_threads = {}
    trader.trade_entered = {}
    trader.ai_optimization_cache = {}
    trader.pattern_analysis_cache = {}
    trader.price_data_points = {}
    trader.advanced_order_managers = {}
    trader.selected_coins = {}
    trader.position_sizing_snapshots = {}
    trader._initialized_exchanges = set()
    trader.trading_cycles = {}
    trader._winrate_window = 10

    trader.update_settings({"default_tp": 0.18, "default_sl": 0.2})

    assert trader.settings["default_tp"] == pytest.approx(0.0018)
    assert trader.settings["default_sl"] == pytest.approx(0.0020)


def test_missing_runtime_profile_does_not_force_balanced_settings():
    class _Chatbot:
        strategy_presets = {"balanced": object()}

        def __init__(self):
            self.actions = []

        def apply_strategy_changes(self, action):
            self.actions.append(action)

    chatbot = _Chatbot()

    trader = object.__new__(Trader)
    trader.settings = {}
    trader.ai_trading_chatbot = chatbot
    trader._runtime_profile_applied = None
    trader.strategy_customizer = None
    trader.log_event = lambda *_args, **_kwargs: None
    trader._apply_connected_strategy_runtime()

    unified = object.__new__(UnifiedTrader)
    unified.settings = {}
    unified.ai_trading_chatbot = chatbot
    unified._runtime_profile_applied = None
    unified.strategy_customizer = None
    unified.log_event = lambda *_args, **_kwargs: None
    unified._apply_connected_strategy_runtime_unified("bybit")

    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    startup_profile_section = main_source.split(
        "def _apply_runtime_strategy_profile", 1
    )[1].split("def _sync_strategy_customizer_profile", 1)[0]

    assert chatbot.actions == []
    assert trader._runtime_profile_applied == ""
    assert unified._runtime_profile_applied == ""
    assert "get('strategy_runtime_profile', '')" in startup_profile_section
    assert "profile = 'balanced'" not in startup_profile_section


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
