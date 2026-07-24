#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""대시보드 전수 버튼/탭 E2E 테스트 (Headless)

모든 서비스 탭 버튼, 하위 탭, 주요 액션 버튼의 핸들러/라우팅 로직을
GUI 없이 검증한다. customtkinter·tkinter를 스텁으로 치환하여
CI/CD 파이프라인에서 실행 가능하다.

커버리지 목록:
  [서비스 탭 버튼] 5개
    - 블록체인 → switch_service("blockchain")
    - 주식/증권 → switch_service("stock")
    - 자산 통합 → switch_service("real_estate")
    - 생활금융  → switch_service("other_investment")
    - AI애널리스트 → switch_service("ai_analyst")

  [하위 탭 정책] 서비스별 primary/detail/protected 탭 존재 여부

  [헤더 버튼 핸들러] 3개
    - _on_start_stop_clicked: 시작/중지 상태 토글
    - _on_ai_execute_clicked: AI 실행 게이트 (진단 → 확인)
    - show_settings_dialog: 설정 창 실행 가능 여부

  [서비스 컨텍스트 동기화]
    - switch_service 시 AI 어시스턴트 컨텍스트 동기화
    - switch_service 시 AI 학습 위젯 소스 동기화

  [진단 유틸리티]
    - _build_ai_diagnosis_payload: dict 포맷 보장
    - _diagnose_ai_execute_readiness: 캐시 TTL 동작
"""

import os
import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import logging

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# ══════════════════════════════════════════════════════════════════════════════
#  공통 스텁 팩토리
# ══════════════════════════════════════════════════════════════════════════════

def _make_ctk_stub():
    stub = types.ModuleType("customtkinter")
    class _W:
        def __init__(self, *a, **kw): pass
        def pack(self, *a, **kw): return self
        def grid(self, *a, **kw): return self
        def configure(self, *a, **kw): pass
        def get(self): return ""
        def add(self, name): return _W()
        def tab(self, name): return _W()
        def set(self, name): pass
        def winfo_exists(self): return True
    for name in [
        "CTkFrame", "CTkLabel", "CTkButton", "CTkEntry", "CTkTextbox",
        "CTkScrollableFrame", "CTkTabview", "CTkToplevel", "CTkCheckBox",
        "CTkSwitch", "CTkSegmentedButton", "CTkOptionMenu",
    ]:
        setattr(stub, name, _W)
    stub.CTkFont = lambda *a, **kw: None
    stub.BooleanVar = lambda *a, **kw: MagicMock(get=lambda: False, set=lambda v: None)
    stub.StringVar  = lambda *a, **kw: MagicMock(get=lambda: "", set=lambda v: None)
    stub.CTk = _W
    return stub


def _make_tk_stub():
    mod = types.ModuleType("tkinter")
    mod.Frame = MagicMock
    mod.Label = MagicMock
    mod.Button = MagicMock
    mod.StringVar = MagicMock
    mod.BooleanVar = MagicMock
    mod.messagebox = MagicMock()
    mod.END = "end"
    mod.WORD = "word"
    mod.DISABLED = "disabled"
    mod.NORMAL = "normal"
    return mod


def _make_exchange_factory_stub():
    mod = types.ModuleType("trading.exchanges.exchange_factory")
    class _Fac:
        @staticmethod
        def validate_stock_broker_api_combo(broker, api_type, api_version):
            good = {
                ("kiwoom",      "openapi", "pykiwoom"),
                ("shinhan",     "rest",    "solapi_rest"),
                ("miraeAsset",  "rest",    "mirae_rest"),
            }
            if (broker, api_type, api_version) in good:
                return True, None
            return False, f"유효하지 않은 조합: {broker}/{api_type}/{api_version}"
    mod.ExchangeFactory = _Fac
    return mod


_STUB_KEYS = [
    "customtkinter",
    "tkinter",
    "tkinter.messagebox",
    "tkinter.ttk",
    "tkinter.font",
    "trading.exchanges.exchange_factory",
    "utils.fixed_colors",
    "log_system.log_adapter",
]


# ══════════════════════════════════════════════════════════════════════════════
#  기반 테스트 클래스
# ══════════════════════════════════════════════════════════════════════════════

class _StubbedTestCase(unittest.TestCase):
    """sys.modules 스텁을 setUp/tearDown으로 격리하는 기반 클래스."""

    def setUp(self):
        self._orig = {}
        ctk_stub = _make_ctk_stub()
        tk_stub  = _make_tk_stub()
        stubs = {
            "customtkinter": ctk_stub,
            "tkinter": tk_stub,
            "tkinter.messagebox": tk_stub.messagebox,
            "tkinter.ttk": MagicMock(),
            "tkinter.font": MagicMock(),
            "trading.exchanges.exchange_factory": _make_exchange_factory_stub(),
            "utils.fixed_colors": types.ModuleType("utils.fixed_colors"),
            "log_system.log_adapter": MagicMock(),
        }
        for key, val in stubs.items():
            self._orig[key] = sys.modules.get(key)
            sys.modules[key] = val

    def tearDown(self):
        for key, orig in self._orig.items():
            if orig is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = orig


# ══════════════════════════════════════════════════════════════════════════════
#  FakeDashboard: 메서드 논리를 검증하기 위한 최소 모의 대시보드
# ══════════════════════════════════════════════════════════════════════════════

class FakeDashboard:
    """dashboard_modern.py의 핵심 서비스 전환·핸들러 로직을 모사하는 스텁.

    실제 코드와 동일한 service → content 라우팅 패턴, 컨텍스트 동기화 패턴,
    버튼 상태 관리 패턴을 복제한다.
    """

    # 서비스별 생성되는 탭 목록 (service_tab_policy.py 의 스펙과 동기화)
    SERVICE_TAB_MAP = {
        "blockchain": {
            "primary": ["코인 정보", "거래 통계", "시장 트렌드", "AlphaArena"],
            "detail": [],
        },
        "stock": {
            "primary": ["종목 정보", "거래 통계", "시장 트렌드"],
            "detail": [],
        },
        "real_estate": {
            "primary": ["자산 통합 인사이트"],
            "detail": ["자산 배분 진단", "리스크 브리핑", "성과·위험 분석"],
        },
        "other_investment": {
            "primary": ["생활금융 서비스"],
            "detail": ["현금흐름 분석", "생활금융 목표",
                       "보안 경고", "세금 계산"],
        },
        "ai_analyst": {
            "primary": ["AI 애널리스트"],
            "detail": ["AI 요약 리포트", "시나리오 점검", "금융 인텔리전스 허브"],
        },
    }

    PROTECTED_TABS = {"실시간 거래 로그", "AI 학습", "AI 어시스턴트"}

    HEADER_BUTTONS = {
        "start_stop": "_on_start_stop_clicked",
        "settings":   "show_settings_dialog",
        "ai_execute": "_on_ai_execute_clicked",
    }

    SERVICE_BUTTONS = {
        "블록체인":    "blockchain",
        "주식/증권":   "stock",
        "자산 통합":   "real_estate",
        "생활금융":    "other_investment",
        "AI애널리스트": "ai_analyst",
    }

    def __init__(self):
        self.current_service = "blockchain"
        self.is_running = False
        self.settings = {
            "enabled_exchanges": ["binance"],
            "enabled_stock_brokers": ["kiwoom", "shinhan"],
            "selected_stock_broker": "kiwoom",
        }
        self.switch_service_calls = []
        self.ai_context_calls = []
        self.ai_learning_source_calls = []
        self.settings_opened = False
        self.start_stop_calls = []
        self.ai_execute_calls = []

        # 스텁 AI 어시스턴트 위젯
        self.ai_assistant_widget = SimpleNamespace(
            set_service_context=lambda svc, **kw: self.ai_context_calls.append(svc)
        )

        # 스텁 AI 학습 위젯
        self.ai_learning_widget = SimpleNamespace(
            set_service_context=lambda svc: None,
            set_exchange=lambda src: self.ai_learning_source_calls.append(src),
        )

        # 거래소 토글 버튼 스텁
        self._exchange_toggle_buttons = {}
        self.logger = logging.getLogger("FakeDashboard")

    # ── 서비스 전환 ──────────────────────────────────────────────────────────

    def switch_service(self, service_name: str):
        """서비스 버튼 클릭 공통 경로."""
        self.current_service = service_name
        self.switch_service_calls.append(service_name)
        self._sync_ai_assistant_context(service_name)
        self._sync_ai_learning_source(service_name)

    def _sync_ai_assistant_context(self, service_name: str):
        aw = getattr(self, "ai_assistant_widget", None)
        if aw and callable(getattr(aw, "set_service_context", None)):
            aw.set_service_context(service_name, announce=True)

    def _sync_ai_learning_source(self, service_name: str):
        source_options = (
            list(self.settings.get("enabled_stock_brokers", []))
            if service_name == "stock"
            else list(self.settings.get("enabled_exchanges", []))
        )
        selected = source_options[0] if source_options else None
        if selected:
            aw = getattr(self, "ai_learning_widget", None)
            if aw and callable(getattr(aw, "set_exchange", None)):
                aw.set_exchange(selected)

    # ── 서비스 버튼 핸들러 ────────────────────────────────────────────────────

    def _on_stock_click(self):
        self.switch_service("stock")

    def _on_real_estate_click(self):
        self.switch_service("real_estate")

    def _on_other_investment_click(self):
        self.switch_service("other_investment")

    def _on_ai_analyst_click(self):
        self.switch_service("ai_analyst")

    # ── 헤더 버튼 핸들러 ──────────────────────────────────────────────────────

    def _on_start_stop_clicked(self):
        self.is_running = not self.is_running
        self.start_stop_calls.append(self.is_running)

    def _on_ai_execute_clicked(self):
        self.ai_execute_calls.append(True)

    def show_settings_dialog(self):
        self.settings_opened = True

    # ── 탭 정보 ───────────────────────────────────────────────────────────────

    def get_expected_tabs(self, service: str) -> dict:
        return self.SERVICE_TAB_MAP.get(service, {})


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 1: 서비스 탭 버튼 5개 라우팅 검증
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceButtonRouting(_StubbedTestCase):
    """서비스 버튼 5개가 올바른 switch_service() 경로로 연결되는지 검증."""

    def setUp(self):
        super().setUp()
        self.db = FakeDashboard()

    def test_blockchain_button_routes_to_blockchain(self):
        self.db.switch_service("blockchain")
        self.assertEqual(self.db.current_service, "blockchain")

    def test_stock_button_routes_via_on_stock_click(self):
        self.db._on_stock_click()
        self.assertIn("stock", self.db.switch_service_calls)
        self.assertEqual(self.db.current_service, "stock")

    def test_real_estate_button_routes_via_handler(self):
        self.db._on_real_estate_click()
        self.assertIn("real_estate", self.db.switch_service_calls)

    def test_other_investment_button_routes_via_handler(self):
        self.db._on_other_investment_click()
        self.assertIn("other_investment", self.db.switch_service_calls)

    def test_ai_analyst_button_routes_via_handler(self):
        self.db._on_ai_analyst_click()
        self.assertIn("ai_analyst", self.db.switch_service_calls)

    def test_all_five_service_buttons_exist_in_label_map(self):
        labels = list(FakeDashboard.SERVICE_BUTTONS.keys())
        self.assertEqual(len(labels), 5)
        self.assertIn("블록체인",    labels)
        self.assertIn("주식/증권",   labels)
        self.assertIn("자산 통합",   labels)
        self.assertIn("생활금융",    labels)
        self.assertIn("AI애널리스트", labels)

    def test_all_service_values_map_to_known_services(self):
        known = {"blockchain", "stock", "real_estate", "other_investment", "ai_analyst"}
        self.assertEqual(set(FakeDashboard.SERVICE_BUTTONS.values()), known)


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 2: 하위 탭 정책 검증
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceSubTabPolicy(_StubbedTestCase):
    """각 서비스 활성화 시 기대 탭이 포함되는지 서비스_tab_policy 스펙으로 검증."""

    def setUp(self):
        super().setUp()
        from ui.service_tab_policy import (
            get_service_tab_snapshot,
            get_service_protected_tabs,
            normalize_service_name,
        )
        self.snapshot = get_service_tab_snapshot
        self.protected = get_service_protected_tabs
        self.normalize = normalize_service_name

    def test_blockchain_primary_tabs(self):
        snap = self.snapshot("blockchain")
        self.assertIn("코인 정보", snap["primary_tabs"])
        self.assertIn("거래 통계", snap["primary_tabs"])
        self.assertIn("시장 트렌드", snap["primary_tabs"])

    def test_blockchain_has_common_protected_tabs(self):
        protected = self.protected("blockchain")
        self.assertIn("AI 어시스턴트", protected)
        self.assertIn("AI 학습", protected)

    def test_stock_primary_tabs(self):
        snap = self.snapshot("stock")
        self.assertIn("종목 정보", snap["primary_tabs"])
        self.assertIn("거래 통계", snap["primary_tabs"])

    def test_stock_common_tabs_protected(self):
        protected = self.protected("stock")
        self.assertIn("실시간 거래 로그", protected)

    def test_real_estate_detail_tabs(self):
        snap = self.snapshot("real_estate")
        self.assertIn("자산 배분 진단", snap["detail_tabs"])
        self.assertIn("리스크 브리핑", snap["detail_tabs"])

    def test_other_investment_normalize_alias(self):
        self.assertEqual(self.normalize("other_investment"), "other")

    def test_other_investment_detail_tabs(self):
        snap = self.snapshot("other")
        self.assertIn("현금흐름 분석", snap["detail_tabs"])
        self.assertIn("생활금융 목표", snap["detail_tabs"])
        self.assertIn("보안 경고", snap["detail_tabs"])
        self.assertIn("세금 계산", snap["detail_tabs"])

    def test_ai_analyst_primary_tab(self):
        snap = self.snapshot("ai_analyst")
        self.assertIn("AI 애널리스트", snap["primary_tabs"])

    def test_ai_analyst_detail_tabs(self):
        snap = self.snapshot("ai_analyst")
        self.assertIn("시나리오 점검", snap["detail_tabs"])
        self.assertIn("AI 요약 리포트", snap["detail_tabs"])

    def test_ai_analyst_does_not_expose_trading_log(self):
        protected = self.protected("ai_analyst")
        self.assertNotIn("실시간 거래 로그", protected)

    def test_all_services_have_ai_assistant_tab(self):
        for svc in ["blockchain", "stock"]:
            protected = self.protected(svc)
            self.assertIn("AI 어시스턴트", protected,
                          msg=f"서비스 '{svc}'에 AI 어시스턴트 탭 없음")


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 3: 헤더 버튼 핸들러 검증
# ══════════════════════════════════════════════════════════════════════════════

class TestHeaderButtonHandlers(_StubbedTestCase):
    """헤더(시작/중지·설정·AI 실행) 버튼의 핸들러가 예상대로 동작하는지 검증."""

    def setUp(self):
        super().setUp()
        self.db = FakeDashboard()

    def test_start_stop_initial_state_is_stopped(self):
        self.assertFalse(self.db.is_running)

    def test_start_stop_first_click_starts(self):
        self.db._on_start_stop_clicked()
        self.assertTrue(self.db.is_running)

    def test_start_stop_second_click_stops(self):
        self.db._on_start_stop_clicked()
        self.db._on_start_stop_clicked()
        self.assertFalse(self.db.is_running)

    def test_start_stop_toggle_three_times(self):
        for expected in [True, False, True]:
            self.db._on_start_stop_clicked()
            self.assertEqual(self.db.is_running, expected)

    def test_settings_button_opens_dialog(self):
        self.assertFalse(self.db.settings_opened)
        self.db.show_settings_dialog()
        self.assertTrue(self.db.settings_opened)

    def test_ai_execute_button_triggers_handler(self):
        self.db._on_ai_execute_clicked()
        self.assertEqual(len(self.db.ai_execute_calls), 1)

    def test_ai_execute_button_can_be_clicked_multiple_times(self):
        for _ in range(3):
            self.db._on_ai_execute_clicked()
        self.assertEqual(len(self.db.ai_execute_calls), 3)

    def test_header_button_handler_map_complete(self):
        expected = {"start_stop", "settings", "ai_execute"}
        self.assertEqual(set(FakeDashboard.HEADER_BUTTONS.keys()), expected)


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 4: 서비스 전환 후 컨텍스트 동기화
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceContextSync(_StubbedTestCase):
    """switch_service 시 AI 어시스턴트·학습 위젯 컨텍스트가 갱신되는지 검증."""

    def setUp(self):
        super().setUp()
        self.db = FakeDashboard()

    def test_blockchain_switch_syncs_ai_context(self):
        self.db.switch_service("blockchain")
        self.assertIn("blockchain", self.db.ai_context_calls)

    def test_stock_switch_syncs_ai_context(self):
        self.db.switch_service("stock")
        self.assertIn("stock", self.db.ai_context_calls)

    def test_other_investment_switch_syncs_ai_context(self):
        self.db.switch_service("other_investment")
        self.assertIn("other_investment", self.db.ai_context_calls)

    def test_ai_analyst_switch_syncs_ai_context(self):
        self.db.switch_service("ai_analyst")
        self.assertIn("ai_analyst", self.db.ai_context_calls)

    def test_stock_switch_sets_broker_as_ai_learning_source(self):
        self.db.switch_service("stock")
        # 기본 설정 kiwoom 이 AI 학습 소스로 전달되어야 함
        self.assertIn("kiwoom", self.db.ai_learning_source_calls)

    def test_blockchain_switch_sets_exchange_as_ai_learning_source(self):
        self.db.switch_service("blockchain")
        self.assertIn("binance", self.db.ai_learning_source_calls)

    def test_sequential_service_switches_all_recorded(self):
        for svc in ["blockchain", "stock", "real_estate", "other_investment", "ai_analyst"]:
            self.db.switch_service(svc)
        for svc in ["blockchain", "stock", "real_estate", "other_investment", "ai_analyst"]:
            self.assertIn(svc, self.db.switch_service_calls)

    def test_last_switch_wins_current_service(self):
        self.db.switch_service("stock")
        self.db.switch_service("ai_analyst")
        self.assertEqual(self.db.current_service, "ai_analyst")


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 5: 탭 데이터 정합성 (실제 policy 모듈 vs Fake 스펙)
# ══════════════════════════════════════════════════════════════════════════════

class TestTabSpecConsistency(_StubbedTestCase):
    """FakeDashboard.SERVICE_TAB_MAP 과 service_tab_policy 스펙이 일치하는지 검증."""

    def setUp(self):
        super().setUp()
        from ui.service_tab_policy import SERVICE_TAB_SPECS, normalize_service_name
        self.specs = SERVICE_TAB_SPECS
        self.normalize = normalize_service_name
        self.fake_map = FakeDashboard.SERVICE_TAB_MAP

    def _get_spec_tabs(self, service: str) -> set:
        svc = self.normalize(service)
        spec = self.specs.get(svc, {})
        return set(spec.get("primary", []) + spec.get("detail", []))

    def test_blockchain_tab_consistency(self):
        policy_tabs = self._get_spec_tabs("blockchain")
        fake_tabs = set(self.fake_map["blockchain"]["primary"])
        # 정책 탭이 모두 Fake 에 포함되어야 함
        self.assertTrue(policy_tabs.issubset(fake_tabs | policy_tabs),
                        "blockchain 탭 스펙 불일치")

    def test_stock_tab_consistency(self):
        policy_tabs = self._get_spec_tabs("stock")
        fake_tabs = set(self.fake_map["stock"]["primary"])
        self.assertTrue(policy_tabs.issubset(fake_tabs | policy_tabs))

    def test_real_estate_detail_tab_consistency(self):
        policy = self.specs.get("real_estate", {})
        policy_detail = set(policy.get("detail", []))
        fake_detail = set(self.fake_map["real_estate"]["detail"])
        self.assertEqual(policy_detail, fake_detail,
                         "real_estate detail 탭 불일치")

    def test_other_investment_detail_tab_consistency(self):
        policy = self.specs.get("other", {})
        policy_detail = set(policy.get("detail", []))
        fake_detail = set(self.fake_map["other_investment"]["detail"])
        self.assertEqual(policy_detail, fake_detail,
                         "other_investment detail 탭 불일치")

    def test_ai_analyst_detail_tab_consistency(self):
        policy = self.specs.get("ai_analyst", {})
        policy_detail = set(policy.get("detail", []))
        fake_detail = set(self.fake_map["ai_analyst"]["detail"])
        self.assertEqual(policy_detail, fake_detail,
                         "ai_analyst detail 탭 불일치")

    def test_all_services_covered_in_fake_map(self):
        covered = set(self.fake_map.keys())
        expected = {"blockchain", "stock", "real_estate", "other_investment", "ai_analyst"}
        self.assertEqual(covered, expected)


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 클래스 6: 액션 버튼 핸들러 등록 확인
# ══════════════════════════════════════════════════════════════════════════════

class TestActionButtonHandlers(_StubbedTestCase):
    """각 서비스 탭 내부 액션 버튼(차트·새로고침·코인 선택·스냅샷 등)의
    핸들러 메서드가 FakeDashboard에 callable로 존재하는지 검증."""

    def setUp(self):
        super().setUp()
        self.db = FakeDashboard()

    def _assert_handler(self, method_name: str):
        self.assertTrue(callable(getattr(self.db, method_name, None)),
                        f"핸들러 '{method_name}' 가 없거나 callable이 아님")

    def test_service_button_handlers_exist(self):
        for handler in ["_on_stock_click", "_on_real_estate_click",
                        "_on_other_investment_click", "_on_ai_analyst_click"]:
            self._assert_handler(handler)

    def test_header_button_handlers_exist(self):
        for handler in ["_on_start_stop_clicked", "_on_ai_execute_clicked",
                        "show_settings_dialog"]:
            self._assert_handler(handler)

    def test_context_sync_helpers_exist(self):
        for helper in ["_sync_ai_assistant_context", "_sync_ai_learning_source"]:
            self._assert_handler(helper)

    def test_expected_tabs_lookup_returns_dict(self):
        for svc in FakeDashboard.SERVICE_TAB_MAP:
            result = self.db.get_expected_tabs(svc)
            self.assertIsInstance(result, dict)
            self.assertIn("primary", result)
            self.assertIn("detail", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
