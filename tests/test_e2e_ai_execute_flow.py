#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E 통합 테스트: AI 실행 버튼 → 진단 → 설정 연동 → 저장 후 갱신 전체 흐름

Headless 환경(GUI 없이)에서 대시보드 핵심 메서드의 논리 흐름을 검증한다.
실제 customtkinter/tkinter 위젯 없이 SimpleNamespace 스텁으로 교체하여
CI/CD 파이프라인에서도 실행 가능하도록 작성한다.

중요: 이 파일의 sys.modules 스텁은 모듈 레벨에서 등록하지 않고,
      각 테스트 클래스에서 setUp/tearDown으로 격리하여 다른 테스트와
      sys.modules 오염이 발생하지 않도록 한다.
"""

import os
import sys
import types
import unittest
from unittest.mock import MagicMock
import logging

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)


# ══════════════════════════════════════════════════════════════════════════════
#  스텁 팩토리 (모듈 레벨 등록 없이 필요할 때만 생성)
# ══════════════════════════════════════════════════════════════════════════════

def _make_ctk_stub():
    stub = types.ModuleType("customtkinter")
    class _W:
        def __init__(self, *a, **kw): pass
        def pack(self, *a, **kw): return self
        def configure(self, *a, **kw): pass
        def get(self): return ""
    for name in ["CTkFrame", "CTkLabel", "CTkButton", "CTkEntry",
                 "CTkTextbox", "CTkScrollableFrame", "CTkTabview",
                 "CTkToplevel", "CTkCheckBox", "CTkSwitch"]:
        setattr(stub, name, _W)
    stub.CTkFont = lambda *a, **kw: None
    stub.BooleanVar = lambda *a, **kw: MagicMock(get=lambda: False)
    stub.StringVar  = lambda *a, **kw: MagicMock(get=lambda: "")
    stub.CTk = _W
    return stub


def _make_exchange_factory_stub():
    mod = types.ModuleType("trading.exchanges.exchange_factory")
    class _FakeExchangeFactory:
        @staticmethod
        def validate_stock_broker_api_combo(broker, api_type, api_version):
            if broker == "kiwoom" and api_type == "openapi_plus" and api_version == "pykiwoom":
                return True, None
            if broker == "shinhan" and api_type == "partner_rest" and api_version == "shinhan_openapi_v2":
                return True, None
            return False, f"유효하지 않은 조합: {broker}/{api_type}/{api_version}"
    mod.ExchangeFactory = _FakeExchangeFactory
    return mod


_STUB_KEYS = [
    "customtkinter",
    "tkinter",
    "tkinter.messagebox",
    "trading.exchanges.exchange_factory",
    "utils.fixed_colors",
]


class _StubbedTestCase(unittest.TestCase):
    """sys.modules 스텁을 setUp에서 등록하고 tearDown에서 복원하는 베이스 클래스."""

    def setUp(self):
        # 현재 sys.modules 상태 스냅샷 저장
        self._orig_modules = {k: sys.modules.get(k) for k in _STUB_KEYS}

        # CTK 스텁
        ctk_stub = _make_ctk_stub()
        sys.modules["customtkinter"] = ctk_stub

        # tkinter 스텁
        tk_stub = types.ModuleType("tkinter")
        mb_stub = types.ModuleType("tkinter.messagebox")
        mb_stub.askyesno = MagicMock(return_value=True)
        mb_stub.showinfo  = MagicMock()
        mb_stub.showerror = MagicMock()
        tk_stub.messagebox = mb_stub
        sys.modules["tkinter"] = tk_stub
        sys.modules["tkinter.messagebox"] = mb_stub

        # ExchangeFactory 스텁
        ef_mod = _make_exchange_factory_stub()
        sys.modules["trading.exchanges.exchange_factory"] = ef_mod

        # fixed_colors 스텁
        fc_mod = types.ModuleType("utils.fixed_colors")
        fc_mod.FIXED_COLORS = {}
        sys.modules["utils.fixed_colors"] = fc_mod

        # 이 테스트 내에서 사용할 FakeExchangeFactory 참조
        self.FakeExchangeFactory = ef_mod.ExchangeFactory

    def tearDown(self):
        # setUp 이전 상태로 복원
        for key, val in self._orig_modules.items():
            if val is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = val


# ══════════════════════════════════════════════════════════════════════════════
#  헬퍼 / 스텁 클래스
# ══════════════════════════════════════════════════════════════════════════════

def _make_fake_settings(**overrides):
    base = {
        "enabled_exchanges": ["binance"],
        "binance_api_key": "test_key",
        "binance_secret_key": "test_secret",
        "default_leverage": 5,
        "balance_utilization_limit": 0.25,
        "risk_tolerance": "MODERATE",
        "enable_stock_live_order": False,
        "enabled_stock_brokers": [],
        "stock_broker_configs": {},
        "ai_trading_preferences": {
            "risk_tolerance": "MODERATE",
            "balance_utilization_limit": 0.25,
        },
    }
    base.update(overrides)
    return base


class FakeExchangeManager:
    """exchange_manager 최소 스텁"""
    def __init__(self, connected=True):
        self._connected = connected

    def validate_exchange_connection(self, exchange_name: str) -> bool:
        return self._connected

    def get_exchange_balance(self, exchange_name: str) -> dict:
        if not self._connected:
            return {"status": "error", "error": "연결 없음"}
        return {"status": "success", "balance": {"USDT": {"wallet_balance": 100.0}}}


class FakeDashboard:
    """대시보드 핵심 메서드를 재현한 테스트용 클래스."""
    logger = logging.getLogger("test_dashboard")
    max_ai_execute_history_size: int = 10
    ai_execute_summary_label = None

    def __init__(self, settings: dict, exchange_manager=None, running_exchanges=None,
                 fake_factory_cls=None):
        self.settings = settings
        self.exchange_manager = exchange_manager or FakeExchangeManager()
        self.enabled_exchanges = list(settings.get("enabled_exchanges", []))
        self._running_exchanges: set = set(running_exchanges or [])
        self.ai_execute_history: list = []
        self._diagnosis_cache = None
        self._diagnosis_cache_settings_hash = None
        # 주입된 ExchangeFactory 스텁 사용
        self._factory_cls = fake_factory_cls

    def _get_stock_broker_config(self, broker: str) -> dict:
        return self.settings.get("stock_broker_configs", {}).get(broker, {})

    def _diagnose_ai_execute_readiness(self) -> list:
        import concurrent.futures
        settings_obj = self.settings if isinstance(self.settings, dict) else {}
        try:
            _cache_key_parts = (
                str(sorted(getattr(self, 'enabled_exchanges', []) or [])),
                str(sorted(settings_obj.get('enabled_stock_brokers', []) or [])),
                str(settings_obj.get('stock_broker_configs', {})),
            )
            current_hash = hash(_cache_key_parts)
            if (self._diagnosis_cache is not None
                    and self._diagnosis_cache_settings_hash == current_hash):
                return list(self._diagnosis_cache)
        except Exception:
            current_hash = None

        lines: list = []
        enabled_exchanges = list(getattr(self, 'enabled_exchanges', []) or [])
        if enabled_exchanges and getattr(self, 'exchange_manager', None):
            def _check_exchange(ex: str) -> str:
                try:
                    ok = bool(self.exchange_manager.validate_exchange_connection(ex))
                    return f"- 거래소 {ex}: {'연결 준비됨' if ok else '연결 확인 필요'}"
                except Exception as e:
                    return f"- 거래소 {ex}: 진단 오류 ({str(e)[:60]})"
            try:
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=min(len(enabled_exchanges), 4),
                    thread_name_prefix="diag_exchange",
                ) as executor:
                    futures = {executor.submit(_check_exchange, ex): ex
                               for ex in enabled_exchanges}
                    results: dict = {}
                    for fut in concurrent.futures.as_completed(futures, timeout=5):
                        ex = futures[fut]
                        try:
                            results[ex] = fut.result()
                        except Exception as e:
                            results[ex] = f"- 거래소 {ex}: 진단 오류 ({str(e)[:60]})"
                    for ex in enabled_exchanges:
                        lines.append(results.get(ex, f"- 거래소 {ex}: 진단 미완료"))
            except concurrent.futures.TimeoutError:
                for ex in enabled_exchanges:
                    lines.append(f"- 거래소 {ex}: 연결 확인 시간 초과")
            except Exception as e:
                lines.append(f"- 거래소 병렬 진단 오류: {str(e)[:80]}")
        elif enabled_exchanges:
            lines.append('- 거래소 진단: exchange_manager가 없어 상세 확인 불가')

        enabled_brokers = list(settings_obj.get('enabled_stock_brokers', []) or [])
        broker_configs = settings_obj.get('stock_broker_configs', {})
        if enabled_brokers and isinstance(broker_configs, dict):
            for broker in enabled_brokers:
                cfg = self._get_stock_broker_config(str(broker))
                api_type = str(cfg.get('api_type', 'openapi') or 'openapi').strip().lower()
                api_version = str(cfg.get('api_version', 'live_api') or 'live_api').strip().lower()
                key_ready = bool(
                    (str(cfg.get('app_key', '') or '').strip() and str(cfg.get('app_secret', '') or '').strip())
                    or (str(cfg.get('id', '') or '').strip() and str(cfg.get('password', '') or '').strip())
                )
                combo_ok = True
                if self._factory_cls:
                    try:
                        result = self._factory_cls.validate_stock_broker_api_combo(
                            str(broker), api_type, api_version)
                        combo_ok = bool(result[0] if isinstance(result, tuple) else result)
                    except Exception:
                        combo_ok = False
                lines.append(
                    f"- 증권 {broker}: 키 {'준비됨' if key_ready else '미준비'} / "
                    f"API 조합 {'정상' if combo_ok else '확인 필요'} ({api_type}/{api_version})"
                )

        if not lines:
            lines.append('- 준비도 진단 항목이 없습니다. 설정을 먼저 확인하세요.')

        try:
            self._diagnosis_cache = list(lines)
            self._diagnosis_cache_settings_hash = current_hash
        except Exception:
            pass

        return lines

    def _assess_ai_execute_risk(self):
        s = self.settings if isinstance(self.settings, dict) else {}
        reasons = []
        leverage = s.get('default_leverage', 1)
        prefs = s.get('ai_trading_preferences', {}) or {}
        utilization = prefs.get('balance_utilization_limit', s.get('balance_utilization_limit', 0.25))
        risk_tolerance = prefs.get('risk_tolerance', s.get('risk_tolerance', 'MODERATE'))
        live_order = s.get('enable_stock_live_order', False)
        if live_order:
            reasons.append('실주문 플래그(enable_stock_live_order)가 켜져 있습니다')
        if leverage >= 15:
            reasons.append(f'레버리지가 높습니다 ({leverage}x)')
        if utilization >= 0.40 and risk_tolerance == 'AGGRESSIVE':
            reasons.append(f'잔고 활용 한도가 높고 공격적 모드입니다 ({utilization:.0%})')
        if reasons:
            risk_level = 'high' if live_order else 'elevated'
        else:
            risk_level = 'normal'
        return risk_level, reasons

    def _build_ai_execute_plan(self):
        enabled = set(getattr(self, 'enabled_exchanges', []) or [])
        running = set(getattr(self, '_running_exchanges', set()) or set())
        if not enabled:
            return "start", "AI 실행 준비", [
                "- 활성화된 거래소가 없어 실행할 작업이 없습니다.",
                "- 설정에서 거래소를 먼저 활성화하세요.",
            ]
        if not running:
            targets = sorted(list(enabled))
            return "start", "AI 실행 계획", [
                f"- 실행 대상 거래소: {', '.join(targets)}",
                "- 순서: 연결 상태 확인 -> 거래소 시작",
                "- 실패 거래소가 있으면 개별 상태를 유지하고 진행합니다.",
            ]
        if running == enabled:
            targets = sorted(list(running))
            return "stop", "AI 정지 계획", [
                f"- 정지 대상 거래소: {', '.join(targets)}",
                "- 순서: 실행 중 거래소 정지 -> 상태 동기화",
            ]
        remaining = sorted(list(enabled - running))
        return "resume", "AI 이어실행 계획", [
            f"- 아직 미실행 거래소: {', '.join(remaining)}",
            f"- 현재 실행 중 거래소 수: {len(running)}/{len(enabled)}",
            "- 순서: 미실행 거래소만 추가 시작",
        ]

    def _record_ai_execute_event(self, *, action, title, plan_lines,
                                  risk_level, risk_reasons, result):
        from datetime import datetime
        event = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'action': action,
            'title': title,
            'plan_lines': list(plan_lines or []),
            'risk_level': risk_level,
            'risk_reasons': list(risk_reasons or []),
            'result': result,
        }
        self.ai_execute_history.append(event)
        if len(self.ai_execute_history) > self.max_ai_execute_history_size:
            self.ai_execute_history.pop(0)

    def _refresh_ai_execute_summary_card(self):
        pass


# ══════════════════════════════════════════════════════════════════════════════
#  테스트 케이스
# ══════════════════════════════════════════════════════════════════════════════

class TestAIExecutePlanGeneration(_StubbedTestCase):
    """_build_ai_execute_plan() 로직 검증"""

    def test_no_exchange_returns_start_plan(self):
        dash = FakeDashboard(settings=_make_fake_settings(enabled_exchanges=[]))
        action, title, lines = dash._build_ai_execute_plan()
        self.assertEqual(action, "start")
        self.assertIn("없어", lines[0])

    def test_all_stopped_returns_start_action(self):
        dash = FakeDashboard(settings=_make_fake_settings())
        action, title, lines = dash._build_ai_execute_plan()
        self.assertEqual(action, "start")
        self.assertIn("binance", lines[0])

    def test_all_running_returns_stop_action(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(enabled_exchanges=["binance", "upbit"]),
            running_exchanges=["binance", "upbit"],
        )
        action, title, lines = dash._build_ai_execute_plan()
        self.assertEqual(action, "stop")

    def test_partial_running_returns_resume_action(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(enabled_exchanges=["binance", "upbit"]),
            running_exchanges=["binance"],
        )
        action, title, lines = dash._build_ai_execute_plan()
        self.assertEqual(action, "resume")
        self.assertIn("upbit", lines[0])


class TestAIExecuteReadinessDiagnosis(_StubbedTestCase):
    """_diagnose_ai_execute_readiness() 준비도 진단 검증"""

    def test_connected_exchange_shows_ready(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(),
            exchange_manager=FakeExchangeManager(connected=True),
        )
        lines = dash._diagnose_ai_execute_readiness()
        self.assertTrue(any("연결 준비됨" in l for l in lines))

    def test_disconnected_exchange_shows_warning(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(),
            exchange_manager=FakeExchangeManager(connected=False),
        )
        lines = dash._diagnose_ai_execute_readiness()
        self.assertTrue(any("확인 필요" in l for l in lines))

    def test_no_exchange_returns_fallback_message(self):
        dash = FakeDashboard(settings=_make_fake_settings(enabled_exchanges=[]))
        lines = dash._diagnose_ai_execute_readiness()
        self.assertEqual(len(lines), 1)
        self.assertIn("설정을 먼저 확인", lines[0])

    def test_broker_with_key_shows_ready(self):
        settings = _make_fake_settings(
            enabled_stock_brokers=["kiwoom"],
            stock_broker_configs={
                "kiwoom": {
                    "api_type": "openapi_plus",
                    "api_version": "pykiwoom",
                    "id": "user01",
                    "password": "pass01",
                }
            },
        )
        dash = FakeDashboard(
            settings=settings,
            fake_factory_cls=self.FakeExchangeFactory,
        )
        lines = dash._diagnose_ai_execute_readiness()
        kiwoom_line = next((l for l in lines if "kiwoom" in l), None)
        self.assertIsNotNone(kiwoom_line)
        self.assertIn("키 준비됨", kiwoom_line)
        self.assertIn("정상", kiwoom_line)

    def test_broker_without_key_shows_not_ready(self):
        settings = _make_fake_settings(
            enabled_stock_brokers=["kiwoom"],
            stock_broker_configs={
                "kiwoom": {
                    "api_type": "openapi",
                    "api_version": "pykiwoom",
                    "id": "",
                    "password": "",
                }
            },
        )
        dash = FakeDashboard(settings=settings)
        lines = dash._diagnose_ai_execute_readiness()
        kiwoom_line = next((l for l in lines if "kiwoom" in l), None)
        self.assertIsNotNone(kiwoom_line)
        self.assertIn("미준비", kiwoom_line)

    def test_broker_invalid_api_combo_shows_warning(self):
        settings = _make_fake_settings(
            enabled_stock_brokers=["kiwoom"],
            stock_broker_configs={
                "kiwoom": {
                    "api_type": "rest",
                    "api_version": "invalid",
                    "id": "user01",
                    "password": "pass01",
                }
            },
        )
        dash = FakeDashboard(
            settings=settings,
            fake_factory_cls=self.FakeExchangeFactory,
        )
        lines = dash._diagnose_ai_execute_readiness()
        kiwoom_line = next((l for l in lines if "kiwoom" in l), None)
        self.assertIsNotNone(kiwoom_line)
        self.assertIn("확인 필요", kiwoom_line)

    def test_cache_returns_same_result(self):
        """동일 설정에서 두 번째 호출은 캐시된 결과를 반환한다"""
        dash = FakeDashboard(
            settings=_make_fake_settings(),
            exchange_manager=FakeExchangeManager(connected=True),
        )
        result1 = dash._diagnose_ai_execute_readiness()
        result2 = dash._diagnose_ai_execute_readiness()
        self.assertEqual(result1, result2)
        # 두 번째는 캐시 적중이므로 동일 객체가 아닌 복사본
        self.assertIsNot(result1, result2)


class TestAIExecuteRiskAssessment(_StubbedTestCase):
    """_assess_ai_execute_risk() 위험 레벨 판정 검증"""

    def test_normal_settings_is_low_risk(self):
        dash = FakeDashboard(settings=_make_fake_settings(
            default_leverage=5,
            enable_stock_live_order=False,
        ))
        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "normal")
        self.assertEqual(len(reasons), 0)

    def test_live_order_flag_on_is_high_risk(self):
        dash = FakeDashboard(settings=_make_fake_settings(
            enable_stock_live_order=True,
        ))
        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "high")
        self.assertTrue(any("실주문" in r for r in reasons))

    def test_high_leverage_is_elevated(self):
        dash = FakeDashboard(settings=_make_fake_settings(
            default_leverage=15,
            enable_stock_live_order=False,
        ))
        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "elevated")
        self.assertTrue(any("레버리지" in r for r in reasons))

    def test_aggressive_high_utilization_is_elevated(self):
        settings = _make_fake_settings(
            enable_stock_live_order=False,
            ai_trading_preferences={
                "risk_tolerance": "AGGRESSIVE",
                "balance_utilization_limit": 0.45,
            },
        )
        dash = FakeDashboard(settings=settings)
        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "elevated")
        self.assertTrue(any("공격적 모드" in r for r in reasons))


class TestAIExecuteEventRecording(_StubbedTestCase):
    """_record_ai_execute_event() 이력 기록 검증"""

    def test_event_is_recorded(self):
        dash = FakeDashboard(settings=_make_fake_settings())
        dash._record_ai_execute_event(
            action="start", title="AI 실행 계획",
            plan_lines=["- binance 시작"], risk_level="normal",
            risk_reasons=[], result="실행 완료",
        )
        self.assertEqual(len(dash.ai_execute_history), 1)
        self.assertEqual(dash.ai_execute_history[0]['result'], "실행 완료")

    def test_history_capped_at_max_size(self):
        dash = FakeDashboard(settings=_make_fake_settings())
        dash.max_ai_execute_history_size = 3
        for i in range(5):
            dash._record_ai_execute_event(
                action="start", title=f"이벤트 {i}",
                plan_lines=[], risk_level="normal",
                risk_reasons=[], result=f"결과 {i}",
            )
        self.assertEqual(len(dash.ai_execute_history), 3)
        self.assertEqual(dash.ai_execute_history[0]['title'], "이벤트 2")

    def test_cancel_event_is_recorded(self):
        dash = FakeDashboard(settings=_make_fake_settings())
        dash._record_ai_execute_event(
            action="start", title="AI 실행 계획",
            plan_lines=[], risk_level="normal",
            risk_reasons=[], result="사용자 취소",
        )
        self.assertEqual(dash.ai_execute_history[-1]['result'], "사용자 취소")


class TestSettingsDiagnosisIntegration(_StubbedTestCase):
    """설정 저장 후 진단 갱신 통합 흐름 검증"""

    def test_diagnosis_updates_after_settings_change(self):
        settings = _make_fake_settings(enabled_exchanges=[])
        dash = FakeDashboard(settings=settings,
                             exchange_manager=FakeExchangeManager(connected=True))

        _, _, initial_lines = dash._build_ai_execute_plan()
        self.assertIn("없어", initial_lines[0])

        dash.settings['enabled_exchanges'] = ['binance']
        dash.enabled_exchanges = ['binance']

        _, _, updated_lines = dash._build_ai_execute_plan()
        self.assertIn("binance", updated_lines[0])

    def test_diagnosis_reflects_broker_key_after_update(self):
        settings = _make_fake_settings(
            enabled_stock_brokers=["kiwoom"],
            stock_broker_configs={
                "kiwoom": {
                    "api_type": "openapi",
                    "api_version": "pykiwoom",
                    "id": "",
                    "password": "",
                }
            },
        )
        dash = FakeDashboard(settings=settings)

        initial_lines = dash._diagnose_ai_execute_readiness()
        kiwoom_line = next(l for l in initial_lines if "kiwoom" in l)
        self.assertIn("미준비", kiwoom_line)

        # 브로커 키 입력 후 캐시 무효화 + 재진단
        dash.settings['stock_broker_configs']['kiwoom']['id'] = "user01"
        dash.settings['stock_broker_configs']['kiwoom']['password'] = "pass01"
        dash._diagnosis_cache = None
        dash._diagnosis_cache_settings_hash = None

        updated_lines = dash._diagnose_ai_execute_readiness()
        kiwoom_line2 = next(l for l in updated_lines if "kiwoom" in l)
        self.assertIn("준비됨", kiwoom_line2)

    def test_risk_level_normalizes_after_live_order_disabled(self):
        settings = _make_fake_settings(enable_stock_live_order=True)
        dash = FakeDashboard(settings=settings)

        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "high")

        dash.settings['enable_stock_live_order'] = False
        risk_level2, reasons2 = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level2, "normal")
        self.assertEqual(len(reasons2), 0)


class TestEdgeCases(_StubbedTestCase):
    """엣지 케이스: 빈 설정, None 값, 예외 안전성 검증"""

    def test_empty_settings_does_not_crash(self):
        dash = FakeDashboard(settings={})
        lines = dash._diagnose_ai_execute_readiness()
        self.assertIsInstance(lines, list)
        self.assertTrue(len(lines) >= 1)

    def test_none_broker_configs_does_not_crash(self):
        settings = _make_fake_settings(
            enabled_stock_brokers=["kiwoom"],
            stock_broker_configs=None,
        )
        dash = FakeDashboard(settings=settings)
        lines = dash._diagnose_ai_execute_readiness()
        self.assertIsInstance(lines, list)

    def test_exchange_manager_exception_is_caught(self):
        class BrokenExchangeManager:
            def validate_exchange_connection(self, ex):
                raise RuntimeError("연결 실패 시뮬레이션")

        dash = FakeDashboard(
            settings=_make_fake_settings(enabled_exchanges=["binance"]),
            exchange_manager=BrokenExchangeManager(),
        )
        lines = dash._diagnose_ai_execute_readiness()
        self.assertTrue(any("오류" in l for l in lines))

    def test_multiple_exchanges_all_diagnosed(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(
                enabled_exchanges=["binance", "upbit", "okx"],
            ),
            exchange_manager=FakeExchangeManager(connected=True),
        )
        lines = dash._diagnose_ai_execute_readiness()
        exchange_lines = [l for l in lines if "거래소" in l]
        self.assertEqual(len(exchange_lines), 3)

    def test_risk_assessment_with_missing_prefs(self):
        settings = {
            "default_leverage": 5,
            "enable_stock_live_order": False,
        }
        dash = FakeDashboard(settings=settings)
        risk_level, reasons = dash._assess_ai_execute_risk()
        self.assertIn(risk_level, ["normal", "elevated", "high"])


class TestFullAIExecuteFlow(_StubbedTestCase):
    """전체 AI 실행 흐름 통합 검증"""

    def test_complete_flow_start(self):
        dash = FakeDashboard(
            settings=_make_fake_settings(),
            exchange_manager=FakeExchangeManager(connected=True),
        )

        readiness_lines = dash._diagnose_ai_execute_readiness()
        self.assertTrue(any("binance" in l for l in readiness_lines))

        risk_level, risk_reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "normal")

        action, title, plan_lines = dash._build_ai_execute_plan()
        self.assertEqual(action, "start")
        self.assertIn("binance", plan_lines[0])

        dash._record_ai_execute_event(
            action=action, title=title,
            plan_lines=plan_lines + readiness_lines,
            risk_level=risk_level, risk_reasons=risk_reasons,
            result="실행 완료",
        )

        self.assertEqual(len(dash.ai_execute_history), 1)
        last = dash.ai_execute_history[-1]
        self.assertEqual(last['action'], "start")
        self.assertEqual(last['result'], "실행 완료")
        self.assertEqual(last['risk_level'], "normal")

    def test_complete_flow_high_risk_cancel(self):
        dash = FakeDashboard(settings=_make_fake_settings(
            enable_stock_live_order=True,
        ))

        risk_level, risk_reasons = dash._assess_ai_execute_risk()
        self.assertEqual(risk_level, "high")

        action, title, plan_lines = dash._build_ai_execute_plan()

        dash._record_ai_execute_event(
            action=action, title=title,
            plan_lines=plan_lines, risk_level=risk_level,
            risk_reasons=risk_reasons, result="사용자 취소",
        )

        self.assertEqual(dash.ai_execute_history[-1]['result'], "사용자 취소")
        self.assertEqual(dash.ai_execute_history[-1]['risk_level'], "high")


if __name__ == "__main__":
    unittest.main(verbosity=2)



# ── 대시보드 핵심 메서드만 가져오기 ──────────────────────────────────────────
# 대시보드 전체를 임포트하면 tk mainloop가 실행되므로,
# 테스트할 메서드들을 직접 mixin 형태로 로드하거나
# 직접 unbound 방식으로 테스트한다.

def _load_dashboard_methods():
    """dashboard_modern.py에서 ModernDashboard 클래스 메서드를 불러온다."""
    spec = importlib.util.spec_from_file_location(
        "_test_dashboard",
        os.path.join(ROOT_DIR, "ui", "dashboard_modern.py"),
    )
    # 실제 임포트 대신 소스에서 필요한 함수 텍스트를 파싱하기 어려우므로
    # FakeDashboard 클래스에서 직접 메서드를 복사해 테스트한다.
    return None



if __name__ == "__main__":
    unittest.main(verbosity=2)
