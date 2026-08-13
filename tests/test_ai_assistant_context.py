#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 어시스턴트 컨텍스트 및 명령 분류 회귀 테스트"""

import os
import sys
import copy
import unittest
import logging
import types
import importlib.util
import tempfile
from pathlib import Path
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

    def test_high_vol_location_question_reports_live_policy_without_applying(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "advanced_trading_layers": {
                    "strategy_engine": {
                        "enabled": True,
                        "high_vol_action": "evaluate",
                        "consensus_threshold": 0.6,
                        "cooldown_sec": 60,
                    }
                }
            }
        )

        result = widget._build_high_vol_support(
            "OpenAI 최신 모델로 검증하면서 high vol 차단을 해제하고 싶은데 어디서 설정하면 될까요?"
        )

        self.assertIsNotNone(result)
        self.assertNotIn("proposal", result)
        self.assertIn("현재 이미 ‘평가 계속’", result["message"])
        self.assertIn("설정 → 고급 매매 계층 → 전략 엔진 세부 설정", result["message"])
        self.assertIn("가드레일", result["message"])
        self.assertIn("보장", result["message"])

    def test_high_vol_explicit_unblock_builds_confirmable_proposal(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "advanced_trading_layers": {
                    "strategy_engine": {
                        "enabled": True,
                        "high_vol_action": "block",
                        "consensus_threshold": 0.6,
                        "cooldown_sec": 60,
                    }
                }
            }
        )

        result = widget._build_high_vol_support("high vol 차단 해제해줘")

        self.assertEqual(
            result["proposal"],
            {"strategy_engine_high_vol_action": "evaluate"},
        )

    def test_ambiguous_model_change_requests_role_clarification(self):
        widget = self._make_widget()

        clarification = widget._build_settings_clarification("모델 바꿔줘")

        self.assertIn("어떤 역할의 모델", clarification)
        self.assertIn("AI 어시스턴트", clarification)

    def test_ai_custom_help_explains_xai_and_real_apply_sequence(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={"ai_custom_runtime": {"enabled": False}}
        )

        response = widget._build_ai_custom_support(
            "유튜브 전략의 XAI 적용값이 실제로 어떻게 AI 커스텀에 적용되나요?"
        )

        self.assertIn("현재 AI 커스텀 실자동매매 사용 스위치: OFF", response)
        self.assertIn("v3.9.0.10 AI Custom Management & Runtime Integrity Update", response)
        self.assertIn("원문의 어느 문장·화면이 어떤 IR 노드", response)
        self.assertIn("Level 1", response)
        self.assertIn("미지원은 차단", response)

    def test_multi_venue_help_reports_current_policy_and_parallel_meaning(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "enabled_exchanges": ["bitget", "okx"],
                "trade_enabled_exchanges": ["bitget", "okx"],
                "enabled_stock_brokers": ["kiwoom"],
                "multi_venue_execution": {"mode": "parallel"},
            }
        )

        response = widget._build_multi_venue_support(
            "같은 BTC 신호가 여러 거래소에 오면 중복 주문 아닌가요?"
        )

        self.assertIn("선택한 각 대상에서 각각 실행", response)
        self.assertIn("bitget, okx", response)
        self.assertIn("양쪽 주문이 정상", response)
        self.assertIn("같은 거래소·같은 계좌·같은 신호", response)

    def test_execution_mode_help_explains_learning_without_live_scope(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "paper_trading": False,
                "enabled_exchanges": ["binance"],
                "trade_enabled_exchanges": [],
            }
        )

        response = widget._build_execution_mode_support(
            "실제 주문 실행 거래소 없이 학습만 하는 건가요?"
        )

        self.assertIn("현재 실행 상태: LEARNING", response)
        self.assertIn("종목선정", response)
        self.assertIn("신규 주문은 보내지 않습니다", response)

    def test_identity_answer_is_always_noahai(self):
        widget = self._make_widget()

        response = widget._build_identity_support("너 누구야")

        self.assertTrue(response.startswith("저는 NoahAI입니다."))


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
        widget._validate_trading_change_context = lambda _settings: (True, [])

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

    def test_typed_action_registry_and_nested_rollback_values_are_consistent(self):
        current = {
            "default_leverage": 4,
            "ai_trading_preferences": {
                "risk_tolerance": "MODERATE",
                "balance_utilization_limit": 0.25,
            },
            "advanced_trading_layers": {
                "strategy_engine": {
                    "high_vol_action": "evaluate",
                    "consensus_threshold": 0.60,
                    "cooldown_sec": 60,
                },
            },
        }
        keys = [
            "default_leverage",
            "risk_tolerance",
            "strategy_engine_high_vol_action",
            "strategy_engine_consensus_threshold",
        ]
        before = AIAssistantWidget._logical_setting_values(current, keys)
        changed = AIAssistantWidget._merge_logical_setting_values(
            current,
            {
                "default_leverage": 2,
                "risk_tolerance": "CONSERVATIVE",
                "strategy_engine_high_vol_action": "block",
                "strategy_engine_consensus_threshold": 0.75,
            },
        )
        restored = AIAssistantWidget._merge_logical_setting_values(changed, before)

        self.assertEqual(
            AIAssistantWidget._logical_setting_values(restored, keys),
            before,
        )
        self.assertTrue(all(
            spec["permission"] == "user_confirm"
            for spec in AIAssistantWidget.SETTINGS_ACTION_REGISTRY.values()
        ))
        self.assertTrue(all(
            spec["permission"] == "disabled"
            for spec in AIAssistantWidget.PROTECTED_ACTION_REGISTRY.values()
        ))

    def test_protected_actions_never_fall_through_as_executed(self):
        widget = self._make_widget()
        order = widget._build_protected_action_support("BTC를 시장가로 매수 주문해줘")
        start = widget._build_protected_action_support("자동매매 시작해줘")
        credentials = widget._build_protected_action_support("API 키를 바꿔줘")
        question = widget._build_protected_action_support("BTC 매수 타이밍을 분석해줘")

        self.assertIn("실행하지 않았습니다", order)
        self.assertIn("실행하지 않았습니다", start)
        self.assertIn("실행하지 않았습니다", credentials)
        self.assertIsNone(question)

    def test_persistent_history_is_user_scoped_shape_and_excludes_secrets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            widget = self._make_widget()
            widget.settings_audit_path = Path(temp_dir) / "assistant" / "settings_change_history.json"
            widget._append_settings_history(
                changes={"default_leverage": 5},
                before_full={"default_leverage": 3, "api_secret": "must-not-persist"},
                after_full={"default_leverage": 5, "api_secret": "must-not-persist"},
                source="test",
            )

            raw = widget.settings_audit_path.read_text(encoding="utf-8")
            self.assertNotIn("must-not-persist", raw)

            restored = self._make_widget()
            restored.settings_audit_path = widget.settings_audit_path
            restored._load_persistent_settings_history()
            self.assertEqual(restored.settings_change_history[-1]["before"]["default_leverage"], 3)
            self.assertEqual(restored.settings_change_history[-1]["after"]["default_leverage"], 5)

    def test_undo_rechecks_persisted_value_and_keeps_history_on_mismatch(self):
        widget = self._make_widget()
        widget.settings_change_history = [{
            "settings": {"default_leverage": 5},
            "before": {"default_leverage": 3},
            "after": {"default_leverage": 5},
        }]
        dashboard = SimpleNamespace(
            settings={"default_leverage": 5},
            on_settings_changed=lambda *_args, **_kwargs: None,
        )
        widget.parent_dashboard = dashboard
        stored = {"default_leverage": 5}
        calls = {"count": 0}
        fake_settings_module = types.ModuleType("config.settings")

        def _save_settings(value):
            calls["count"] += 1
            stored.clear()
            stored.update(copy.deepcopy(value))
            if calls["count"] == 1:
                stored["default_leverage"] = 4
            return True

        fake_settings_module.save_settings = _save_settings
        fake_settings_module.load_settings = lambda: copy.deepcopy(stored)

        with patch.dict(sys.modules, {"config.settings": fake_settings_module}):
            widget.undo_last_settings_change()

        self.assertEqual(stored["default_leverage"], 5)
        self.assertEqual(dashboard.settings["default_leverage"], 5)
        self.assertEqual(len(widget.settings_change_history), 1)
        self.assertTrue(any("현재 설정을 유지" in message for message in widget.messages))

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
        widget._validate_trading_change_context = lambda _settings: (True, [])

        fake_settings_module = types.ModuleType("config.settings")
        persisted = copy.deepcopy(initial_settings)

        def _save_settings(value):
            persisted.clear()
            persisted.update(copy.deepcopy(value))
            return True

        fake_settings_module.save_settings = _save_settings
        fake_settings_module.load_settings = lambda: copy.deepcopy(persisted)

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

    def test_strategy_engine_settings_are_sanitized_and_saved_nested(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "advanced_trading_layers": {
                    "strategy_engine": {
                        "enabled": True,
                        "high_vol_action": "block",
                        "consensus_threshold": 0.6,
                        "cooldown_sec": 60,
                    }
                }
            },
            on_settings_changed=lambda *_args, **_kwargs: None,
        )
        widget.require_final_settings_confirmation = True
        widget._validate_trading_change_context = lambda _settings: (True, [])
        fake_settings_module = types.ModuleType("config.settings")
        saved = {}

        def _save_settings(value):
            saved.clear()
            saved.update(value)
            return True

        fake_settings_module.save_settings = _save_settings
        fake_settings_module.load_settings = lambda: copy.deepcopy(saved)

        safe, notes = widget._sanitize_settings_proposal(
            {
                "strategy_engine_high_vol_action": "evaluate",
                "strategy_engine_consensus_threshold": 2.0,
                "strategy_engine_cooldown_sec": -10,
            }
        )
        self.assertEqual(safe["strategy_engine_high_vol_action"], "evaluate")
        self.assertEqual(safe["strategy_engine_consensus_threshold"], 0.95)
        self.assertEqual(safe["strategy_engine_cooldown_sec"], 0)
        self.assertTrue(notes)

        with patch.dict(sys.modules, {"config.settings": fake_settings_module}):
            widget._apply_settings_automatically(
                {"strategy_engine_high_vol_action": "evaluate"},
                "high vol 차단 해제해줘",
            )

        policy = saved["advanced_trading_layers"]["strategy_engine"]
        self.assertEqual(policy["high_vol_action"], "evaluate")
        self.assertNotIn("strategy_engine_high_vol_action", saved)

    def test_latest_and_provider_model_names_do_not_require_hardcoded_allowlist(self):
        widget = self._make_widget()

        safe, notes = widget._sanitize_settings_proposal(
            {
                "assistant_ai_model": "gpt-5.6-terra",
                "ai_model_roles": {
                    "frequent_cheap": "provider/model-mini",
                    "premium": "gpt-5.6-sol",
                },
            }
        )

        self.assertEqual(safe["assistant_ai_model"], "gpt-5.6-terra")
        self.assertEqual(safe["ai_model_roles"]["premium"], "gpt-5.6-sol")
        self.assertFalse(notes)

        unsafe, unsafe_notes = widget._sanitize_settings_proposal(
            {"assistant_ai_model": "gpt-5.6-sol; rm -rf /"}
        )
        self.assertNotIn("assistant_ai_model", unsafe)
        self.assertTrue(unsafe_notes)

    def test_ai_auto_is_coerced_to_mandatory_user_confirmation(self):
        widget = self._make_widget()

        safe, notes = widget._sanitize_settings_proposal(
            {"assistant_apply_mode": "ai_auto"}
        )

        self.assertEqual(safe["assistant_apply_mode"], "user_confirm")
        self.assertTrue(any("자동적용" in note for note in notes))

    def test_final_confirmation_cannot_be_disabled_by_legacy_flag(self):
        widget = self._make_widget()
        widget.require_final_settings_confirmation = False

        with patch.object(module.messagebox, "askyesno", return_value=False) as confirm:
            applied = widget._confirm_settings_apply({"default_leverage": 2})

        self.assertFalse(applied)
        confirm.assert_called_once()

    def test_risk_increase_is_blocked_when_market_or_performance_context_is_missing(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "default_leverage": 3,
                "default_sl": 0.01,
                "ai_trading_preferences": {
                    "risk_tolerance": "MODERATE",
                    "balance_utilization_limit": 0.25,
                },
            }
        )
        widget._get_current_trading_context = lambda: (
            "현재 서비스: blockchain\n"
            "거래 통계: 기록 없음 (첫 거래 후 표시됩니다)\n"
            "활성 포지션: 없음"
        )

        allowed, reasons = widget._validate_trading_change_context(
            {"default_leverage": 5}
        )

        self.assertFalse(allowed)
        self.assertTrue(any("시장 데이터" in reason for reason in reasons))
        self.assertTrue(any("거래 성과" in reason for reason in reasons))

    def test_conservative_change_remains_available_without_market_context(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={
                "default_leverage": 5,
                "default_sl": 0.02,
                "ai_trading_preferences": {
                    "risk_tolerance": "AGGRESSIVE",
                    "balance_utilization_limit": 0.40,
                },
            }
        )
        widget._get_current_trading_context = lambda: ""

        allowed, reasons = widget._validate_trading_change_context(
            {
                "default_leverage": 2,
                "risk_tolerance": "CONSERVATIVE",
                "balance_utilization_limit": 0.15,
            }
        )

        self.assertTrue(allowed)
        self.assertFalse(reasons)

    def test_save_path_rechecks_context_and_blocks_stale_risk_increase(self):
        widget = self._make_widget()
        widget.parent_dashboard = SimpleNamespace(
            settings={"default_leverage": 3},
            on_settings_changed=lambda *_args, **_kwargs: None,
        )
        widget.settings_change_history = []
        widget.max_history_size = 50
        widget.messages = []
        widget.add_ai_message = lambda message: widget.messages.append(message)
        widget._validate_trading_change_context = lambda _settings: (
            False,
            ["제안 이후 열린 포지션이 확인됐습니다."],
        )
        fake_settings_module = types.ModuleType("config.settings")
        saved = []
        fake_settings_module.save_settings = lambda value: saved.append(value) or True

        with patch.dict(sys.modules, {"config.settings": fake_settings_module}):
            widget._apply_settings_automatically(
                {"default_leverage": 5},
                "레버리지 올려줘",
            )

        self.assertFalse(saved)
        self.assertEqual(widget.parent_dashboard.settings["default_leverage"], 3)
        self.assertTrue(any("저장 직전 안전 재검증" in message for message in widget.messages))

    def test_question_exchange_overrides_screen_selection_and_shows_effective_leverage(self):
        widget = self._make_widget()
        unified = SimpleNamespace(
            active_positions={"upbit": {}},
            last_effective_trade_params={
                "upbit": {
                    "BTC/KRW": {
                        "configured_leverage": 10,
                        "effective_leverage": 1,
                        "leverage_reason": "현물 거래소는 레버리지를 사용하지 않음",
                    }
                }
            },
            last_trade_decisions={
                "upbit": {
                    "BTC/KRW": {
                        "status": "skipped",
                        "reason": "최소 주문금액 미달",
                        "recorded_at": "2026-08-11T00:00:00+00:00",
                    }
                }
            },
        )
        widget.parent_dashboard = SimpleNamespace(
            current_service="blockchain",
            exchange_manager=FakeExchangeManager(),
            settings={
                "selected_exchange": "binance",
                "default_leverage": 10,
                "default_tp": 0.0018,
                "default_sl": 0.0020,
            },
            recorder=FakeRecorder(),
            trader=None,
            unified_trader=unified,
            selected_coins=[],
        )

        context = widget._get_current_trading_context("업비트는 왜 거래하지 않았나요?")

        self.assertIn("화면 선택 거래소: binance", context)
        self.assertIn("질문 대상 거래소: upbit", context)
        self.assertIn("설정 레버리지 상한: 10x (실제 주문 레버리지가 아님)", context)
        self.assertIn("설정상한 10x → 실제 1x", context)
        self.assertIn("최소 주문금액 미달", context)


if __name__ == "__main__":
    unittest.main()
