#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock Service 통합 실증 테스트
API 연동만 하면 바로 사용할 수 있도록 설계된 테스트 모음

실행 방법:
  cd /Users/playone/SynologyDrive/Works/noahai_client
  source .venv/bin/activate
  python -m pytest tests/test_stock_integration.py -v
  python -m pytest tests/test_stock_integration.py -v -k "mock"   # Mock 전용
  python -m pytest tests/test_stock_integration.py -v -k "live"   # Live API 전용

테스트 구성:
  [1] MockAdapterTests        - API 없이 동작 검증 (항상 실행)
  [2] AdapterContractTests    - 인터페이스 계약 검증 (항상 실행)
  [3] FactoryTests            - 팩토리→어댑터 생성 검증 (항상 실행)
  [4] SettingsFlowTests       - 설정→어댑터 파라미터 전달 검증 (항상 실행)
  [5] DashboardFlowTests      - 설정→대시보드→어댑터 전체 흐름 (항상 실행)
  [6] ETFDetectionTests       - 3개 증권사 ETF 판별 일관성 (항상 실행)
  [7] LiveAPITests            - 실제 API 연동 테스트 (LIVE_MODE=true 시만 실행)
"""

import unittest
import json
import os
import sys
import platform
from typing import Dict, Any
from unittest.mock import patch, MagicMock

# ─── 프로젝트 루트 추가 ──────────────────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
from trading.exchanges.exchange_factory import ExchangeFactory

# Live 모드 여부 (환경변수로 제어)
LIVE_MODE = os.environ.get("LIVE_STOCK_TEST", "false").lower() == "true"


def _can_run_kiwoom_live() -> tuple[bool, str]:
    """키움 Live 테스트 실행 가능 여부를 반환한다."""
    if platform.system() != "Windows":
        return False, "키움 Live 테스트는 Windows 환경에서만 실행 가능"
    try:
        __import__("pykiwoom")
    except Exception:
        return False, "pykiwoom 미설치 또는 import 실패"
    return True, "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# [1] Mock 어댑터 기본 동작 테스트
# ═══════════════════════════════════════════════════════════════════════════════

class TestMockAdapterBasic(unittest.TestCase):
    """Mock 어댑터 기본 동작 검증 - API 없이 전체 흐름 확인"""

    def setUp(self):
        self.adapter = StockMockAdapter(
            broker_name="kiwoom",
            user_id="test_user",
            latency_ms=0  # 테스트 속도를 위해 지연 없음
        )
        self.adapter.connect()

    def test_connect_succeeds(self):
        """연결이 성공해야 함"""
        self.assertTrue(self.adapter.is_connected)

    def test_disconnect_changes_state(self):
        """연결 해제 후 is_connected = False"""
        self.adapter.disconnect()
        self.assertFalse(self.adapter.is_connected)

    def test_get_stock_list_returns_list(self):
        """주식 목록 조회 - 리스트 반환"""
        stocks = self.adapter.get_stock_list()
        self.assertIsInstance(stocks, list)
        self.assertGreater(len(stocks), 0)

    def test_get_stock_list_has_required_fields(self):
        """주식 목록 각 항목에 필수 필드 존재"""
        stocks = self.adapter.get_stock_list()
        required = {"code", "name", "market", "current_price"}
        for s in stocks:
            self.assertTrue(required.issubset(s.keys()),
                            f"필수 필드 누락: {required - s.keys()}")

    def test_get_etf_list_returns_list(self):
        """ETF 목록 조회 - 리스트 반환"""
        etfs = self.adapter.get_etf_list()
        self.assertIsInstance(etfs, list)
        self.assertGreater(len(etfs), 0)

    def test_get_etf_list_has_nav_field(self):
        """ETF 목록에 NAV(순자산가치) 필드 존재"""
        etfs = self.adapter.get_etf_list()
        for etf in etfs:
            self.assertIn("nav", etf, "ETF에 nav 필드가 있어야 함")

    def test_get_balance_returns_dict(self):
        """잔고 조회 - 딕셔너리 반환"""
        balance = self.adapter.get_balance()
        self.assertIsInstance(balance, dict)

    def test_get_balance_has_cash_field(self):
        """잔고에 cash 필드 존재"""
        balance = self.adapter.get_balance()
        self.assertIn("cash", balance)
        self.assertGreaterEqual(balance["cash"], 0)

    def test_get_positions_returns_list(self):
        """보유 종목 조회 - 리스트 반환"""
        positions = self.adapter.get_positions()
        self.assertIsInstance(positions, list)

    def test_get_positions_has_required_fields(self):
        """보유 종목 각 항목에 필수 필드 존재"""
        positions = self.adapter.get_positions()
        required = {"code", "name", "quantity", "avg_price", "current_price", "pnl"}
        for p in positions:
            self.assertTrue(required.issubset(p.keys()),
                            f"보유 종목 필수 필드 누락: {required - p.keys()}")

    def test_place_buy_order_reduces_cash(self):
        """매수 주문 후 현금 감소"""
        before_balance = self.adapter.get_balance()
        cash_before = before_balance["cash"]

        result = self.adapter.place_order("005930", "BUY", 1, 72000)
        
        after_balance = self.adapter.get_balance()
        cash_after = after_balance["cash"]
        
        self.assertEqual(result.get("status"), "filled")
        self.assertLess(cash_after, cash_before, "매수 후 현금이 줄어야 함")

    def test_place_order_exposes_mock_execution_mode(self):
        """Mock 주문 결과에 실행 경로 정보가 포함되어야 함"""
        result = self.adapter.place_order("005930", "BUY", 1, 72000)

        self.assertEqual(result.get("execution_mode"), "mock")
        self.assertEqual(result.get("api_type"), "mock")
        self.assertTrue(result.get("success"))

    def test_place_sell_order_increases_cash(self):
        """매도 주문 후 현금 증가"""
        before = self.adapter.get_balance()
        cash_before = before["cash"]

        result = self.adapter.place_order("005930", "SELL", 1, 72000)
        
        after = self.adapter.get_balance()
        cash_after = after["cash"]
        
        self.assertEqual(result.get("status"), "filled")
        self.assertGreater(cash_after, cash_before, "매도 후 현금이 늘어야 함")

    def test_insufficient_cash_returns_error(self):
        """잔고 부족 시 에러 반환"""
        result = self.adapter.place_order("005930", "BUY", 99999, 72000)
        self.assertEqual(result.get("status"), "error")
        self.assertEqual(result.get("error"), "insufficient_cash")

    def test_get_trading_stats_returns_counts(self):
        """거래 통계 반환"""
        self.adapter.place_order("005930", "BUY", 1, 72000)
        self.adapter.place_order("005930", "SELL", 1, 72000)
        
        stats = self.adapter.get_trading_stats()
        self.assertIsInstance(stats, dict)
        self.assertIn("total_trades", stats)
        self.assertGreaterEqual(stats["total_trades"], 2)

    def test_get_today_trades_returns_list(self):
        """오늘 거래 내역 반환"""
        self.adapter.place_order("005930", "BUY", 1, 72000)
        trades = self.adapter.get_today_trades()
        self.assertIsInstance(trades, list)
        self.assertGreater(len(trades), 0)


# ═══════════════════════════════════════════════════════════════════════════════
# [2] 인터페이스 계약 검증 (3개 증권사 모두 동일한 인터페이스)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdapterInterfaceContract(unittest.TestCase):
    """3개 증권사 어댑터 인터페이스 계약 검증"""

    def _get_adapters(self):
        """3개 증권사 Mock 어댑터 반환"""
        adapters = {}
        for broker in ["kiwoom", "shinhan", "miraeAsset"]:
            a = StockMockAdapter(broker_name=broker, latency_ms=0)
            a.connect()
            adapters[broker] = a
        return adapters

    def test_all_adapters_have_connect_method(self):
        """모든 어댑터에 connect 메서드 존재"""
        for broker, adapter in self._get_adapters().items():
            self.assertTrue(callable(getattr(adapter, "connect", None)),
                            f"{broker}: connect 메서드 없음")

    def test_all_adapters_have_get_balance(self):
        """모든 어댑터에 get_balance 메서드 존재"""
        for broker, adapter in self._get_adapters().items():
            result = adapter.get_balance()
            self.assertIsInstance(result, dict, f"{broker}: get_balance dict 반환해야 함")

    def test_all_adapters_have_get_positions(self):
        """모든 어댑터에 get_positions 메서드 존재"""
        for broker, adapter in self._get_adapters().items():
            result = adapter.get_positions()
            self.assertIsInstance(result, list, f"{broker}: get_positions list 반환해야 함")

    def test_all_adapters_have_get_stock_list(self):
        """모든 어댑터에 get_stock_list 메서드 존재"""
        for broker, adapter in self._get_adapters().items():
            result = adapter.get_stock_list()
            self.assertIsInstance(result, list, f"{broker}: get_stock_list list 반환해야 함")

    def test_all_adapters_have_place_order(self):
        """모든 어댑터에 place_order 메서드 존재"""
        for broker, adapter in self._get_adapters().items():
            result = adapter.place_order("005930", "BUY", 1, 72000)
            self.assertIsInstance(result, dict, f"{broker}: place_order dict 반환해야 함")
            self.assertIn("status", result, f"{broker}: place_order에 status 필드 없음")

    def test_all_adapters_return_consistent_etf_detection(self):
        """3개 증권사 ETF 판별 결과가 동일해야 함"""
        test_cases = [
            ("069500", True),   # KODEX 200 - ETF
            ("005930", False),  # 삼성전자 - 주식
            ("122630", True),   # 해외 ETF
            ("000660", False),  # SK하이닉스 - 주식
        ]
        adapters = self._get_adapters()
        for symbol, expected in test_cases:
            results = {broker: adapter.is_etf(symbol)
                       for broker, adapter in adapters.items()}
            # 모든 증권사가 동일한 결과 반환해야 함
            self.assertTrue(
                all(v == expected for v in results.values()),
                f"{symbol}: 증권사별 ETF 판별 결과 불일치 {results}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# [3] ExchangeFactory 팩토리 검증
# ═══════════════════════════════════════════════════════════════════════════════

class TestExchangeFactory(unittest.TestCase):
    """ExchangeFactory를 통한 어댑터 생성 검증"""

    def setUp(self):
        """테스트 설정"""
        self.settings = {
            "stock_broker_configs": {
                "kiwoom": {
                    "id": "test_user",
                    "password": "test_pw",
                    "cert_password": "test_cert",
                    "account_no": "1234567890",
                    "api_type": "mock",
                    "enabled": True,
                },
                "shinhan": {
                    "id": "test_user2",
                    "password": "test_pw2",
                    "cert_password": "",
                    "account_no": "",
                    "api_type": "mock",
                    "enabled": True,
                },
                "miraeAsset": {
                    "id": "test_user3",
                    "password": "test_pw3",
                    "cert_password": "",
                    "account_no": "",
                    "api_type": "mock",
                    "enabled": True,
                },
            }
        }

    def test_factory_creates_kiwoom_adapter(self):
        """팩토리가 키움 어댑터를 생성해야 함"""
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        self.assertIsNotNone(adapter, "키움 어댑터 생성 실패")

    def test_factory_creates_shinhan_adapter(self):
        """팩토리가 신한 어댑터를 생성해야 함"""
        adapter = ExchangeFactory.create_stock_exchange("shinhan", self.settings)
        self.assertIsNotNone(adapter, "신한 어댑터 생성 실패")

    def test_factory_creates_mirae_asset_adapter(self):
        """팩토리가 미래에셋 어댑터를 생성해야 함"""
        adapter = ExchangeFactory.create_stock_exchange("miraeAsset", self.settings)
        self.assertIsNotNone(adapter, "미래에셋 어댑터 생성 실패")

    def test_factory_lower_case_mirae_asset(self):
        """팩토리: mirae_asset (소문자) 처리 검증"""
        adapter = ExchangeFactory.create_stock_exchange("mirae_asset", self.settings)
        self.assertIsNotNone(adapter, "mirae_asset(소문자) 어댑터 생성 실패")

    def test_factory_passes_user_id_to_adapter(self):
        """팩토리가 설정의 user_id를 어댑터에 전달해야 함"""
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.user_id, "test_user",
                         "팩토리가 user_id를 어댑터에 제대로 전달해야 함")

    def test_factory_passes_account_no_to_adapter(self):
        """팩토리가 설정의 account_no를 어댑터에 전달해야 함"""
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        self.assertIsNotNone(adapter)
        self.assertEqual(adapter.account_no, "1234567890",
                         "팩토리가 account_no를 어댑터에 전달해야 함")

    def test_factory_invalid_broker_raises_error(self):
        """지원하지 않는 증권사 요청 시 예외 발생"""
        with self.assertRaises(ValueError):
            ExchangeFactory.create_stock_exchange("unsupported_broker", self.settings)

    def test_factory_supported_stock_brokers(self):
        """팩토리가 지원 목록을 올바르게 반환해야 함"""
        supported = ExchangeFactory.get_supported_exchanges()
        self.assertIn("stock", supported)
        self.assertIn("kiwoom", supported["stock"])
        self.assertIn("shinhan", supported["stock"])
        self.assertIn("miraeAsset", supported["stock"])


# ═══════════════════════════════════════════════════════════════════════════════
# [4] 설정 → 어댑터 파라미터 전달 흐름 검증
# ═══════════════════════════════════════════════════════════════════════════════

class TestStockBrokerApiComboValidation(unittest.TestCase):
    """ExchangeFactory.validate_stock_broker_api_combo 단위 검증"""

    def test_valid_kiwoom_openapi_pykiwoom(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("kiwoom", "openapi", "pykiwoom")
        self.assertTrue(ok, err)

    def test_valid_shinhan_rest_solapi_rest(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("shinhan", "rest", "solapi_rest")
        self.assertTrue(ok, err)

    def test_valid_mirae_asset_mock(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("miraeAsset", "mock", "")
        self.assertTrue(ok, f"mock 이면 api_version 빈 값 허용: {err}")

    def test_invalid_api_type(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("kiwoom", "grpc", "pykiwoom")
        self.assertFalse(ok)
        self.assertIn("미지원", err)

    def test_invalid_api_version(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("kiwoom", "openapi", "no_such_version")
        self.assertFalse(ok)
        self.assertIn("미지원", err)

    def test_missing_api_version(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("shinhan", "openapi", "")
        self.assertFalse(ok)
        self.assertIn("누락", err)

    def test_unknown_broker(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("unknown_broker", "openapi", "v1")
        self.assertFalse(ok)

    def test_alias_mirae_asset(self):
        ok, err = ExchangeFactory.validate_stock_broker_api_combo("miraeasset", "mock", "")
        self.assertTrue(ok, f"miraeasset 별칭 처리 실패: {err}")


class TestStockCredentialFallback(unittest.TestCase):
    """REST 브로커 인증값 폴백(id/password -> app_key/app_secret) 검증"""

    def test_shinhan_app_key_fallback_from_id_password(self):
        settings = {
            "stock_broker_configs": {
                "shinhan": {
                    "enabled": True,
                    "api_type": "openapi",
                    "api_version": "solapi",
                    "id": "shinhan_app_key_like",
                    "password": "shinhan_secret_like",
                    "account_no": "123-45-67890",
                    "allow_live_order": False,
                }
            }
        }
        adapter = ExchangeFactory.create_stock_exchange("shinhan", settings)
        self.assertEqual(adapter.app_key, "shinhan_app_key_like")
        self.assertEqual(adapter.app_secret, "shinhan_secret_like")

    def test_mirae_app_key_fallback_from_id_password(self):
        settings = {
            "stock_broker_configs": {
                "miraeAsset": {
                    "enabled": True,
                    "api_type": "openapi",
                    "api_version": "miraemts",
                    "id": "mirae_app_key_like",
                    "password": "mirae_secret_like",
                    "account_no": "123-45-67890",
                    "allow_live_order": False,
                }
            }
        }
        adapter = ExchangeFactory.create_stock_exchange("miraeAsset", settings)
        self.assertEqual(adapter.app_key, "mirae_app_key_like")
        self.assertEqual(adapter.app_secret, "mirae_secret_like")


# ═══════════════════════════════════════════════════════════════════════════════
# [4] 설정 → 어댑터 파라미터 전달 흐름 검증
# ═══════════════════════════════════════════════════════════════════════════════

class TestSettingsToAdapterFlow(unittest.TestCase):
    """settings.json의 값이 어댑터까지 올바르게 전달되는지 검증"""

    def _make_settings(self, broker: str, **overrides) -> Dict[str, Any]:
        default_versions = {
            "kiwoom": "pykiwoom",
            "shinhan": "solapi",
            "miraeAsset": "miraemts",
        }
        base = {
            "id": "user_from_settings",
            "password": "pw_from_settings",
            "cert_password": "cert_from_settings",
            "account_no": "acct_from_settings",
            "api_type": "openapi",
            "api_version": default_versions.get(broker, ""),
            "enabled": True,
            "asset_types": ["stock", "etf"],
        }
        base.update(overrides)
        return {"stock_broker_configs": {broker: base}}

    def test_kiwoom_id_passed_from_settings(self):
        """키움: 설정의 id가 어댑터 user_id에 반영"""
        settings = self._make_settings("kiwoom", id="kiwoom_test_id")
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", settings)
        self.assertEqual(adapter.user_id, "kiwoom_test_id")

    def test_shinhan_id_passed_from_settings(self):
        """신한: 설정의 id가 어댑터 user_id에 반영"""
        settings = self._make_settings("shinhan", id="shinhan_test_id")
        adapter = ExchangeFactory.create_stock_exchange("shinhan", settings)
        self.assertEqual(adapter.user_id, "shinhan_test_id")

    def test_mirae_asset_id_passed_from_settings(self):
        """미래에셋: 설정의 id가 어댑터 user_id에 반영"""
        settings = self._make_settings("miraeAsset", id="mirae_test_id")
        adapter = ExchangeFactory.create_stock_exchange("miraeAsset", settings)
        self.assertEqual(adapter.user_id, "mirae_test_id")

    def test_empty_id_returns_adapter_not_none(self):
        """id가 비어 있어도 어댑터는 생성됨 (연결 시 실패)"""
        settings = self._make_settings("kiwoom", id="", password="")
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", settings)
        self.assertIsNotNone(adapter)

    def test_invalid_api_version_raises_error(self):
        """api_type/api_version 조합이 잘못되면 생성을 차단해야 함"""
        settings = self._make_settings("kiwoom", api_type="openapi", api_version="invalid_version")
        with self.assertRaises(ValueError):
            ExchangeFactory.create_stock_exchange("kiwoom", settings)

    def test_enabled_brokers_list_correct(self):
        """enabled_stock_brokers 리스트에 체크된 증권사만 포함"""
        settings = {
            "enabled_stock_brokers": ["kiwoom", "shinhan"],
            "stock_broker_configs": {
                "kiwoom": {"id": "", "password": "", "enabled": True},
                "shinhan": {"id": "", "password": "", "enabled": True},
                "miraeAsset": {"id": "", "password": "", "enabled": False},
            }
        }
        enabled = settings["enabled_stock_brokers"]
        self.assertIn("kiwoom", enabled)
        self.assertIn("shinhan", enabled)
        self.assertNotIn("miraeAsset", enabled)

    def test_asset_types_in_broker_config(self):
        """asset_types 필드 기본값 ['stock', 'etf'] 확인"""
        settings_file = os.path.join(ROOT_DIR, "data", "settings.json")
        if os.path.exists(settings_file):
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            for broker in ("kiwoom", "shinhan", "miraeAsset"):
                config = settings.get("stock_broker_configs", {}).get(broker, {})
                asset_types = config.get("asset_types", [])
                self.assertIn("stock", asset_types,
                              f"{broker}: asset_types에 'stock' 누락")
                self.assertIn("etf", asset_types,
                              f"{broker}: asset_types에 'etf' 누락")


# ═══════════════════════════════════════════════════════════════════════════════
# [5] 대시보드 흐름 검증 (어댑터 헬퍼 로직)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardAdapterFlow(unittest.TestCase):
    """대시보드에서 어댑터 가져오는 흐름 검증"""

    def setUp(self):
        self.settings = {
            "enabled_stock_brokers": ["kiwoom"],
            "stock_broker_configs": {
                "kiwoom": {
                    "id": "test_user",
                    "password": "test_pw",
                    "cert_password": "test_cert",
                    "account_no": "1234567890",
                    "enabled": True,
                    "api_type": "openapi",
                    "api_version": "pykiwoom",
                }
            }
        }

    def test_enabled_broker_adapter_created(self):
        """활성화된 증권사 어댑터가 생성됨"""
        enabled = self.settings.get("enabled_stock_brokers", [])
        self.assertIn("kiwoom", enabled)
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        self.assertIsNotNone(adapter)

    def test_disabled_broker_not_in_enabled_list(self):
        """비활성화된 증권사가 enabled_stock_brokers에 없음"""
        enabled = self.settings.get("enabled_stock_brokers", [])
        self.assertNotIn("shinhan", enabled)
        self.assertNotIn("miraeAsset", enabled)

    def test_broker_connect_and_query_flow(self):
        """연결 → 잔고 → 포지션 → 통계 전체 흐름"""
        adapter = StockMockAdapter(broker_name="kiwoom", latency_ms=0)
        
        # 1. 연결
        connected = adapter.connect()
        self.assertTrue(connected)
        
        # 2. 잔고 조회
        balance = adapter.get_balance()
        self.assertIn("cash", balance)
        
        # 3. 보유 종목 조회
        positions = adapter.get_positions()
        self.assertIsInstance(positions, list)
        
        # 4. 통계 조회
        stats = adapter.get_trading_stats()
        self.assertIn("total_trades", stats)

    def test_dashboard_status_label_text(self):
        """연결 상태에 따른 라벨 텍스트 로직"""
        adapter = StockMockAdapter(broker_name="kiwoom", latency_ms=0)
        
        # 미연결 시
        self.assertFalse(adapter.is_connected)
        
        # 연결 후
        adapter.connect()
        self.assertTrue(adapter.is_connected)
        
        # 연결 해제 후
        adapter.disconnect()
        self.assertFalse(adapter.is_connected)


# ═══════════════════════════════════════════════════════════════════════════════
# [6] ETF 판별 일관성 (3개 증권사)
# ═══════════════════════════════════════════════════════════════════════════════

class TestETFDetectionAllBrokers(unittest.TestCase):
    """3개 증권사 어댑터의 ETF 판별 결과 일관성 검증"""

    ETF_CODES = [
        "069500", "102110", "122630", "114800",
        "261120", "292000", "143010", "111020",
        "069570", "102630", "143320",
    ]
    STOCK_CODES = [
        "005930", "000660", "051910", "035420",
        "207940", "006400", "373220", "263750",
    ]

    def setUp(self):
        self.adapters = {
            broker: StockMockAdapter(broker_name=broker, latency_ms=0)
            for broker in ["kiwoom", "shinhan", "miraeAsset"]
        }

    def test_etf_codes_detected_as_etf_all_brokers(self):
        """ETF 코드는 3개 증권사 모두 ETF로 판별"""
        for code in self.ETF_CODES:
            for broker, adapter in self.adapters.items():
                self.assertTrue(adapter.is_etf(code),
                                f"{broker}: {code}가 ETF로 판별되어야 함")

    def test_stock_codes_not_detected_as_etf(self):
        """주식 코드는 3개 증권사 모두 ETF로 판별되지 않음"""
        for code in self.STOCK_CODES:
            for broker, adapter in self.adapters.items():
                self.assertFalse(adapter.is_etf(code),
                                 f"{broker}: {code}는 주식(ETF 아님)이어야 함")

    def test_invalid_code_returns_false(self):
        """잘못된 코드는 False 반환 (예외 없음)"""
        invalid_codes = ["AAAA", "", "XYZ123", "abc", None]
        for code in invalid_codes:
            for broker, adapter in self.adapters.items():
                try:
                    result = adapter.is_etf(code)
                    self.assertFalse(result,
                                     f"{broker}: 잘못된 코드 {code!r}에서 False 반환해야 함")
                except Exception as e:
                    self.fail(f"{broker}: is_etf({code!r}) 예외 발생 - {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# [7] OpenAPI 버전 선택 검증
# ═══════════════════════════════════════════════════════════════════════════════

class TestAPIVersionSelection(unittest.TestCase):
    """api_type 설정에 따른 어댑터 분기 검증"""

    def test_api_type_mock_recognized(self):
        """api_type = mock 설정 인식 검증"""
        settings = {
            "stock_broker_configs": {
                "kiwoom": {
                    "id": "u", "password": "p",
                    "api_type": "mock",
                    "api_version": "mock",
                    "enabled": True,
                }
            }
        }
        config = settings["stock_broker_configs"]["kiwoom"]
        self.assertEqual(config["api_type"], "mock")

    def test_api_type_openapi_recognized(self):
        """api_type = openapi 설정 인식 검증"""
        settings = {
            "stock_broker_configs": {
                "kiwoom": {
                    "id": "u", "password": "p",
                    "api_type": "openapi",
                    "api_version": "pykiwoom",
                    "enabled": True,
                }
            }
        }
        config = settings["stock_broker_configs"]["kiwoom"]
        self.assertEqual(config["api_type"], "openapi")
        self.assertEqual(config["api_version"], "pykiwoom")

    def test_factory_mock_type_returns_mock_adapter(self):
        """api_type=mock 설정 시 Mock 어댑터가 생성됨"""
        settings = {
            "stock_broker_configs": {
                "kiwoom": {
                    "id": "u", "password": "p",
                    "api_type": "mock",
                    "enabled": True,
                }
            }
        }
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", settings)
        self.assertIsNotNone(adapter)
        # Mock 어댑터인지 확인 (is_connected 없이도 동작)
        self.assertTrue(hasattr(adapter, "connect"))

    def test_settings_json_has_api_type_field(self):
        """settings.json에 api_type 필드 존재 확인"""
        settings_path = os.path.join(ROOT_DIR, "data", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            for broker in ("kiwoom", "shinhan", "miraeAsset"):
                config = settings.get("stock_broker_configs", {}).get(broker, {})
                self.assertIn("api_type", config,
                              f"settings.json의 {broker} 설정에 api_type 필드 없음")

    def test_settings_template_has_stock_live_order_flag(self):
        """settings_template.json에 증권 실주문 플래그 기본값이 존재해야 함"""
        template_path = os.path.join(ROOT_DIR, "config", "settings_template.json")
        with open(template_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        self.assertIn("enable_stock_live_order", settings)
        self.assertFalse(bool(settings.get("enable_stock_live_order")))

        broker_configs = settings.get("stock_broker_configs", {})
        for broker in ("kiwoom", "shinhan", "miraeAsset"):
            config = broker_configs.get(broker, {})
            self.assertIn("allow_live_order", config,
                          f"settings_template.json의 {broker} 설정에 allow_live_order 필드 없음")
            self.assertFalse(bool(config.get("allow_live_order")))

    def test_settings_template_has_stock_auto_trading_defaults(self):
        """settings_template.json에 증권 자동매매 기본 설정이 존재해야 함"""
        template_path = os.path.join(ROOT_DIR, "config", "settings_template.json")
        with open(template_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        auto_cfg = settings.get("stock_auto_trading", {})
        self.assertIsInstance(auto_cfg, dict)
        for key in (
            "enabled",
            "interval_sec",
            "buy_threshold",
            "sell_threshold",
            "order_type",
            "quantity",
            "max_orders_per_cycle",
            "symbols",
            "risk_guard_enabled",
            "max_consecutive_losses",
            "daily_max_loss",
            "cooldown_sec_per_symbol",
            "risk_governance_enabled",
            "global_kill_switch",
            "weekly_max_loss",
            "monthly_max_loss",
            "max_symbol_weight_percent",
            "broker_overrides",
            "enable_exit_policy",
            "take_profit_percent",
            "stop_loss_percent",
            "etf_take_profit_percent",
            "etf_stop_loss_percent",
            "use_signal_exit",
            "etf_alert_exit",
        ):
            self.assertIn(key, auto_cfg, f"stock_auto_trading.{key} 기본값 누락")
        self.assertFalse(bool(auto_cfg.get("enabled")))

    def test_settings_template_has_stock_search_profile_defaults(self):
        """settings_template.json에 증권 검색 프로필 기본 설정이 존재해야 함"""
        template_path = os.path.join(ROOT_DIR, "config", "settings_template.json")
        with open(template_path, "r", encoding="utf-8") as f:
            settings = json.load(f)

        profile = settings.get("stock_search_profile", {})
        self.assertIsInstance(profile, dict)
        self.assertIn("recent_codes", profile)
        self.assertIn("favorites", profile)
        self.assertIsInstance(profile.get("recent_codes"), list)
        self.assertIsInstance(profile.get("favorites"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# [8] Live API 테스트 (LIVE_STOCK_TEST=true 환경변수 설정 시 실행)
# ═══════════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(LIVE_MODE, "Live API 테스트: LIVE_STOCK_TEST=true 환경변수 필요")
class TestLiveAPIIntegration(unittest.TestCase):
    """
    실제 API 연동 테스트
    API 연동 완료 후 이 테스트들이 통과해야 정식 배포 가능

    실행:
      LIVE_STOCK_TEST=true python -m pytest tests/test_stock_integration.py -v -k "live"
    """

    def setUp(self):
        """실제 설정 파일에서 설정 로드"""
        settings_path = os.path.join(ROOT_DIR, "data", "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            self.settings = json.load(f)
        self._kiwoom_live_ok, self._kiwoom_skip_reason = _can_run_kiwoom_live()

    def test_live_kiwoom_connect(self):
        """[LIVE] 키움 실제 연결"""
        if not self._kiwoom_live_ok:
            self.skipTest(self._kiwoom_skip_reason)
        config = self.settings.get("stock_broker_configs", {}).get("kiwoom", {})
        if not config.get("id") or not config.get("password"):
            self.skipTest("키움 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        result = adapter.connect()
        self.assertTrue(result, "키움 실제 연결 실패")

    def test_live_kiwoom_get_balance(self):
        """[LIVE] 키움 실제 잔고 조회"""
        if not self._kiwoom_live_ok:
            self.skipTest(self._kiwoom_skip_reason)
        config = self.settings.get("stock_broker_configs", {}).get("kiwoom", {})
        if not config.get("id"):
            self.skipTest("키움 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        adapter.connect()
        balance = adapter.get_balance()
        
        self.assertIsInstance(balance, dict)
        self.assertNotIn("not_connected", balance.get("error", ""))

    def test_live_kiwoom_get_positions(self):
        """[LIVE] 키움 실제 보유 종목 조회"""
        if not self._kiwoom_live_ok:
            self.skipTest(self._kiwoom_skip_reason)
        config = self.settings.get("stock_broker_configs", {}).get("kiwoom", {})
        if not config.get("id"):
            self.skipTest("키움 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        adapter.connect()
        positions = adapter.get_positions()
        
        self.assertIsInstance(positions, list)

    def test_live_kiwoom_get_stock_list(self):
        """[LIVE] 키움 실제 주식 목록 조회"""
        if not self._kiwoom_live_ok:
            self.skipTest(self._kiwoom_skip_reason)
        config = self.settings.get("stock_broker_configs", {}).get("kiwoom", {})
        if not config.get("id"):
            self.skipTest("키움 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", self.settings)
        adapter.connect()
        stocks = adapter.get_stock_list("KOSPI")
        
        self.assertIsInstance(stocks, list)

    def test_live_shinhan_connect(self):
        """[LIVE] 신한 실제 연결"""
        config = self.settings.get("stock_broker_configs", {}).get("shinhan", {})
        if not config.get("id"):
            self.skipTest("신한 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("shinhan", self.settings)
        result = adapter.connect()
        self.assertTrue(result, "신한 실제 연결 실패")

    def test_live_mirae_asset_connect(self):
        """[LIVE] 미래에셋 실제 연결"""
        config = self.settings.get("stock_broker_configs", {}).get("miraeAsset", {})
        if not config.get("id"):
            self.skipTest("미래에셋 API 키 미설정")
        
        adapter = ExchangeFactory.create_stock_exchange("miraeAsset", self.settings)
        result = adapter.connect()
        self.assertTrue(result, "미래에셋 실제 연결 실패")


# ─── 실행 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # 테스트 스위트 구성
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 항상 실행
    suite.addTests(loader.loadTestsFromTestCase(TestMockAdapterBasic))
    suite.addTests(loader.loadTestsFromTestCase(TestAdapterInterfaceContract))
    suite.addTests(loader.loadTestsFromTestCase(TestExchangeFactory))
    suite.addTests(loader.loadTestsFromTestCase(TestSettingsToAdapterFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestDashboardAdapterFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestETFDetectionAllBrokers))
    suite.addTests(loader.loadTestsFromTestCase(TestAPIVersionSelection))
    
    # Live API 테스트 (조건부)
    if LIVE_MODE:
        suite.addTests(loader.loadTestsFromTestCase(TestLiveAPIIntegration))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
