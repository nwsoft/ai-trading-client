#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 어시스턴트 컨텍스트 및 명령 분류 회귀 테스트"""

import os
import sys
import unittest
import logging
import types
import importlib.util
from unittest.mock import patch
from types import SimpleNamespace

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# headless 테스트용 customtkinter 최소 스텁
ctk_stub = types.ModuleType("customtkinter")
ctk_stub.CTkFrame = object
ctk_stub.CTkLabel = object
ctk_stub.CTkButton = object
ctk_stub.CTkTextbox = object
ctk_stub.CTkEntry = object
ctk_stub.CTkCheckBox = object
ctk_stub.CTkScrollableFrame = object
ctk_stub.CTkTabview = object
ctk_stub.CTkFont = lambda *args, **kwargs: None
sys.modules.setdefault("customtkinter", ctk_stub)

widget_path = os.path.join(ROOT_DIR, "ui", "widgets", "ai_assistant_widget.py")
spec = importlib.util.spec_from_file_location("test_ai_assistant_widget_module", widget_path)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)
AIAssistantWidget = module.AIAssistantWidget


class FakeExchangeManager:
    def __init__(self):
        self.settings = {"selected_exchange": "binance"}
        self.binance_client = SimpleNamespace(is_connected=True)

    def validate_exchange_connection(self, exchange_name):
        return True

    def get_exchange_balance(self, exchange_name):
        return {
            "status": "success",
            "balance": {
                "USDT": {
                    "wallet_balance": 125.5,
                    "unrealized_profit": 2.3,
                    "margin_balance": 127.8,
                    "available_balance": 100.0,
                },
                "BTC": {
                    "wallet_balance": 0.015,
                    "unrealized_profit": 0.0,
                    "margin_balance": 0.015,
                    "available_balance": 0.010,
                },
            },
        }

    def get_24h_ticker(self, symbol, exchange_name):
        return {"last": 100.0, "percentage": 1.2, "quoteVolume": 12345}


class FakeRecorder:
    def get_trading_stats(self):
        return (10, 6, 4, 60.0, 12.5, 1.2)


class AIAssistantContextTests(unittest.TestCase):
    def _make_widget(self):
        widget = AIAssistantWidget.__new__(AIAssistantWidget)
        widget.logger = logging.getLogger("test_ai_assistant")
        widget.parent_dashboard = None
        return widget

    def test_binance_balance_context_handles_nested_balance_dicts(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            exchange_manager=FakeExchangeManager(),
            settings={
                "default_leverage": 3,
                "default_tp": 0.02,
                "default_sl": 0.01,
                "min_trade_amount": 5,
                "ai_trading_preferences": {
                    "risk_tolerance": "MODERATE",
                    "balance_utilization_limit": 0.25,
                },
            },
            recorder=FakeRecorder(),
            trader=None,
            unified_trader=None,
            selected_coins=[],
        )

        context = widget._get_current_trading_context()

        self.assertIn("잔고:", context)
        self.assertNotIn("잔고: 조회 오류", context)
        self.assertIn("USDT", context)
        self.assertIn("총 USDT 가치", context)

    def test_binance_positions_are_included_from_trader_when_unified_trader_absent(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            exchange_manager=FakeExchangeManager(),
            settings={"default_leverage": 3, "default_tp": 0.02, "default_sl": 0.01},
            recorder=FakeRecorder(),
            trader=SimpleNamespace(
                active_positions={
                    "BTCUSDT": {
                        "size": 0.01,
                        "side": "LONG",
                        "entry_price": 60000.0,
                        "current_price": 61000.0,
                        "pnl": 10.0,
                    }
                }
            ),
            unified_trader=None,
            selected_coins=[],
        )

        context = widget._get_current_trading_context()

        self.assertIn("활성 포지션:", context)
        self.assertIn("BTCUSDT", context)

    def test_position_increase_request_is_treated_as_settings_change(self):
        widget = self._make_widget()
        self.assertTrue(widget._is_settings_change_request("포지션을 늘려줘"))
        self.assertTrue(widget._is_settings_change_request("비중을 조금 더 높여줘"))


class _FakeTextBox:
    def __init__(self):
        self.state = "normal"
        self.content = ""

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def delete(self, *_args, **_kwargs):
        self.content = ""

    def insert(self, _pos, text):
        self.content = text


class _FakeButton:
    def __init__(self):
        self.state = None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.text_color = None

    def configure(self, **kwargs):
        if "text" in kwargs:
            self.text = kwargs["text"]
        if "text_color" in kwargs:
            self.text_color = kwargs["text_color"]


class AIAssistantSettingsHistoryTests(unittest.TestCase):
    def _make_widget(self):
        widget = AIAssistantWidget.__new__(AIAssistantWidget)
        widget.logger = logging.getLogger("test_ai_assistant_settings")
        widget.settings_change_history = []
        widget.max_history_size = 50
        widget._settings_modal_info_text = None
        widget._settings_modal_undo_btn = None
        widget.strategy_status_label = None
        widget.ai_manager = SimpleNamespace(enabled=lambda: True)
        widget._color = lambda *_args, **_kwargs: "#22c55e"
        widget.messages = []
        widget.add_ai_message = lambda msg: widget.messages.append(msg)
        return widget

    def test_strategy_status_reflects_live_settings(self):
        widget = self._make_widget()
        widget.strategy_status_label = _FakeLabel()

        widget.update_strategy_status(
            {
                "default_leverage": 7,
                "default_tp": 0.015,
                "default_sl": 0.008,
                "ai_trading_preferences": {
                    "risk_tolerance": "AGGRESSIVE",
                    "balance_utilization_limit": 0.40,
                },
            }
        )

        self.assertIn("전략: 적극 모드", widget.strategy_status_label.text)
        self.assertIn("레버리지: 7x", widget.strategy_status_label.text)
        self.assertIn("잔고 활용 한도: 40%", widget.strategy_status_label.text)

    def test_restore_default_strategy_applies_loaded_settings(self):
        widget = self._make_widget()
        widget.strategy_status_label = _FakeLabel()
        dashboard = SimpleNamespace(
            settings={"default_leverage": 10, "default_tp": 0.03, "default_sl": 0.02},
            on_settings_changed=lambda *_args, **_kwargs: None,
        )
        widget.parent_dashboard = dashboard

        fake_settings_module = types.ModuleType("config.settings")
        fake_settings_module.reset_settings = lambda: True
        fake_settings_module.load_settings = lambda: {
            "default_leverage": 2,
            "default_tp": 0.01,
            "default_sl": 0.005,
            "ai_trading_preferences": {
                "risk_tolerance": "CONSERVATIVE",
                "balance_utilization_limit": 0.10,
            },
        }

        with patch("tkinter.messagebox.askyesno", return_value=True), patch.dict(
            sys.modules, {"config.settings": fake_settings_module}
        ):
            widget.restore_default_strategy()

        self.assertEqual(dashboard.settings["default_leverage"], 2)
        self.assertEqual(dashboard.settings["default_tp"], 0.01)
        self.assertEqual(dashboard.settings["default_sl"], 0.005)
        self.assertIn("전략: 보수 모드", widget.strategy_status_label.text)

    def test_auto_apply_keeps_full_before_snapshot_and_undo_restores_nested_settings(self):
        widget = self._make_widget()
        initial_settings = {
            "default_leverage": 3,
            "default_tp": 0.02,
            "default_sl": 0.01,
            "ai_trading_preferences": {
                "risk_tolerance": "MODERATE",
                "balance_utilization_limit": 0.25,
            },
        }
        dashboard = SimpleNamespace(
            settings={
                "default_leverage": 3,
                "default_tp": 0.02,
                "default_sl": 0.01,
                "ai_trading_preferences": {
                    "risk_tolerance": "MODERATE",
                    "balance_utilization_limit": 0.25,
                },
            },
            on_settings_changed=lambda *_args, **_kwargs: None,
        )
        widget.parent_dashboard = dashboard

        fake_settings_module = types.ModuleType("config.settings")
        fake_settings_module.save_settings = lambda *_args, **_kwargs: True

        with patch.dict(sys.modules, {"config.settings": fake_settings_module}):
            widget._apply_settings_automatically(
                {"default_leverage": 5, "risk_tolerance": "AGGRESSIVE"},
                "레버리지 올려줘",
            )

            self.assertEqual(dashboard.settings["default_leverage"], 5)
            self.assertEqual(
                dashboard.settings["ai_trading_preferences"]["risk_tolerance"],
                "AGGRESSIVE",
            )

            self.assertEqual(len(widget.settings_change_history), 1)
            history = widget.settings_change_history[-1]
            self.assertIn("before_full", history)
            self.assertEqual(history["before_full"], initial_settings)

            widget.undo_last_settings_change()

        self.assertEqual(dashboard.settings, initial_settings)
        self.assertEqual(len(widget.settings_change_history), 0)

    def test_modal_ui_state_updates_by_history(self):
        widget = self._make_widget()
        fake_btn = _FakeButton()
        fake_text = _FakeTextBox()
        widget._settings_modal_undo_btn = fake_btn
        widget._settings_modal_info_text = fake_text

        widget._update_settings_modal_ui_state()
        self.assertEqual(fake_btn.state, "disabled")
        self.assertIn("비활성화", fake_text.content)

        widget.settings_change_history.append({"before_full": {"default_leverage": 3}})
        widget._update_settings_modal_ui_state()
        self.assertEqual(fake_btn.state, "normal")
        self.assertIn("활성화", fake_text.content)

    def test_classify_settings_risk_marks_high_risk_changes(self):
        widget = self._make_widget()

        level, reasons = widget._classify_settings_risk(
            {
                "default_leverage": 15,
                "balance_utilization_limit": 0.40,
                "risk_tolerance": "AGGRESSIVE",
            }
        )

        self.assertEqual(level, "high")
        self.assertTrue(any("레버리지 15x" in reason for reason in reasons))
        self.assertTrue(any("잔고 활용 한도 40%" in reason for reason in reasons))

    def test_build_settings_diff_lines_shows_before_after_values(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "default_leverage": 3,
                "default_tp": 0.02,
                "default_sl": 0.01,
                "ai_trading_preferences": {
                    "risk_tolerance": "MODERATE",
                    "balance_utilization_limit": 0.25,
                },
            }
        )

        lines = widget._build_settings_diff_lines(
            {
                "default_leverage": 5,
                "risk_tolerance": "AGGRESSIVE",
                "balance_utilization_limit": 0.35,
            }
        )

        self.assertIn("- default_leverage: 3x -> 5x", lines)
        self.assertIn("- risk_tolerance: 균형 -> 적극적", lines)
        self.assertIn("- balance_utilization_limit: 25.00% -> 35.00%", lines)


if __name__ == "__main__":
    unittest.main()
