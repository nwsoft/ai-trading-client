#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""초기 AI 온보딩(5문항) E2E 로직 테스트.

GUI 없이 온보딩 상태머신의 핵심 동작을 검증한다.
- 정상 완료 시 설정 적용 호출
- 중도 취소 시 설정 미적용
"""

import os
import sys
import types
import unittest
import logging
import importlib.util
from unittest.mock import MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

_STUB_KEYS = [
    "customtkinter",
    "tkinter",
    "tkinter.messagebox",
]


def _make_ctk_stub():
    stub = types.ModuleType("customtkinter")

    class _W:
        def __init__(self, *a, **kw):
            pass

        def pack(self, *a, **kw):
            return self

        def grid(self, *a, **kw):
            return self

        def configure(self, *a, **kw):
            pass

        def destroy(self):
            pass

        def winfo_children(self):
            return []

        def update(self):
            pass

        _parent_canvas = types.SimpleNamespace(yview_moveto=lambda *_: None)

    for name in [
        "CTkFrame", "CTkLabel", "CTkButton", "CTkTextbox", "CTkEntry",
        "CTkCheckBox", "CTkScrollableFrame", "CTkTabview", "CTkToplevel",
    ]:
        setattr(stub, name, _W)

    stub.CTkFont = lambda *a, **kw: None
    stub.BooleanVar = lambda *a, **kw: MagicMock(get=lambda: False)
    stub.StringVar = lambda *a, **kw: MagicMock(get=lambda: "")
    stub.CTk = _W
    return stub


class _StubbedTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_modules = {k: sys.modules.get(k) for k in _STUB_KEYS}

        ctk_stub = _make_ctk_stub()
        tk_stub = types.ModuleType("tkinter")
        mb_stub = types.ModuleType("tkinter.messagebox")
        mb_stub.askyesno = MagicMock(return_value=True)
        mb_stub.showinfo = MagicMock()
        mb_stub.showerror = MagicMock()
        tk_stub.messagebox = mb_stub

        sys.modules["customtkinter"] = ctk_stub
        sys.modules["tkinter"] = tk_stub
        sys.modules["tkinter.messagebox"] = mb_stub

    def tearDown(self):
        for key, val in self._orig_modules.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val


class TestAIOnboardingFlow(_StubbedTestCase):
    def _make_widget(self):
        module_name = "test_ai_assistant_widget_runtime"
        module_path = os.path.join(ROOT_DIR, "ui", "widgets", "ai_assistant_widget.py")
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("ai_assistant_widget 모듈 로드 스펙 생성 실패")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        AIAssistantWidget = module.AIAssistantWidget

        widget = object.__new__(AIAssistantWidget)
        widget.logger = logging.getLogger("test_ai_onboarding")
        widget._onboarding_active = False
        widget._onboarding_step = 0
        widget._onboarding_answers = {}
        widget._onboarding_source = ""
        widget.require_final_settings_confirmation = True

        widget._messages = []
        widget.add_ai_message = lambda msg: widget._messages.append(str(msg))

        widget._applied_payload = None
        widget._confirm_settings_apply = lambda payload: True
        widget._apply_settings_automatically = (
            lambda payload, reason: setattr(widget, "_applied_payload", {"payload": payload, "reason": reason})
        )

        return widget

    def test_onboarding_complete_applies_settings(self):
        widget = self._make_widget()

        widget.start_initial_onboarding(source="test")
        self.assertTrue(widget._onboarding_active)

        # goal / risk(high) / budget(save) / apply_mode(auto) / recheck(7days)
        widget._consume_onboarding_answer("1")
        widget._consume_onboarding_answer("3")
        widget._consume_onboarding_answer("1")
        widget._consume_onboarding_answer("2")
        widget._consume_onboarding_answer("1")

        self.assertFalse(widget._onboarding_active)
        self.assertIsNotNone(widget._applied_payload)

        payload = widget._applied_payload["payload"]
        # 고위험 선택 시 1차 완화 정책 적용 확인
        self.assertEqual(payload.get("risk_tolerance"), "MODERATE")
        self.assertLessEqual(float(payload.get("balance_utilization_limit", 1.0)), 0.25)
        self.assertEqual(payload.get("assistant_apply_mode"), "user_confirm")
        self.assertEqual(payload.get("openai_model"), "gpt-4o-mini")
        self.assertIn("ai_model_roles", payload)

    def test_onboarding_cancel_does_not_apply(self):
        widget = self._make_widget()

        widget.start_initial_onboarding(source="test")
        self.assertTrue(widget._onboarding_active)

        handled = widget._consume_onboarding_answer("취소")

        self.assertTrue(handled)
        self.assertFalse(widget._onboarding_active)
        self.assertIsNone(widget._applied_payload)


if __name__ == "__main__":
    unittest.main()
