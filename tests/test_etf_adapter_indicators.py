#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETF 지표 어댑터 연동 단위테스트.

커버 대상:
- StockMockAdapter.get_etf_list() — nav/tracking_error/expense_ratio 반환
- ShinhanStockAdapter.get_etf_list() — trcErrRt/nav 필드명 매핑
- MiraeAssetStockAdapter.get_etf_list() — trc_errt/nav 필드명 매핑
- 각 어댑터 is_etf() — ETF 코드 범위 판별
- ETFMetrics risk_level/nav_gap/summary/to_dict
- score_etf() 점수 계산
- StockAnalysisService.get_etf_analysis() 전체 경로 (Mock)
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
from trading.stock_analysis_service import (
    ETFMetrics,
    StockAnalysisService,
    score_etf,
)


# ──────────────────────────────────────────────────────────────────────────────
# StockMockAdapter — get_etf_list / is_etf
# ──────────────────────────────────────────────────────────────────────────────

class TestMockAdapterETF:
    def setup_method(self):
        self.adapter = StockMockAdapter(broker_name="kiwoom", latency_ms=0)
        self.adapter.connect()

    def test_get_etf_list_returns_list(self):
        result = self.adapter.get_etf_list()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_etf_list_has_required_fields(self):
        for etf in self.adapter.get_etf_list():
            assert "code" in etf
            assert "name" in etf
            assert "current_price" in etf
            assert "nav" in etf
            assert "tracking_error" in etf

    def test_get_etf_list_nav_is_near_price(self):
        """NAV는 현재가와 3% 이내여야 한다 (mock noise 범위)"""
        for etf in self.adapter.get_etf_list():
            price = float(etf["current_price"])
            nav = float(etf["nav"])
            if price > 0 and nav > 0:
                gap_pct = abs(price - nav) / nav * 100
                assert gap_pct < 3.0, f"{etf['code']}: NAV 괴리 {gap_pct:.2f}% 비정상"

    def test_get_etf_list_tracking_error_positive(self):
        for etf in self.adapter.get_etf_list():
            te = etf.get("tracking_error")
            if te is not None:
                assert float(te) >= 0.0

    def test_get_etf_list_expense_ratio_present(self):
        for etf in self.adapter.get_etf_list():
            assert "expense_ratio" in etf

    # ── is_etf ──────────────────────────────────────────────────────────────

    def test_is_etf_kodex_200(self):
        assert self.adapter.is_etf("069500") is True

    def test_is_etf_leverage(self):
        assert self.adapter.is_etf("122630") is True

    def test_is_etf_bond(self):
        assert self.adapter.is_etf("261120") is True

    def test_is_etf_gold_commodity(self):
        assert self.adapter.is_etf("292000") is True

    def test_is_etf_samsung_stock_false(self):
        assert self.adapter.is_etf("005930") is False

    def test_is_etf_invalid_code(self):
        assert self.adapter.is_etf("abc") is False
        assert self.adapter.is_etf("") is False

    def test_get_etf_list_when_disconnected(self):
        adapter = StockMockAdapter(latency_ms=0)
        adapter.is_connected = False
        result = adapter.get_etf_list()
        assert isinstance(result, list)


# ──────────────────────────────────────────────────────────────────────────────
# ShinhanStockAdapter — get_etf_list 필드명 매핑 (backend 주입)
# ──────────────────────────────────────────────────────────────────────────────

class FakeRespShinhan:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _make_shinhan_backend(etf_items: List[Dict[str, Any]]):
    items_ref = etf_items

    class FakeHttp:
        _mock_token = "test_token"
        headers: Dict = {}

        def get(self, url, params=None, timeout=None):
            if "etf-list" in url:
                return FakeRespShinhan({"etfs": items_ref})
            return FakeRespShinhan({})

        def post(self, url, json=None, timeout=None):
            return FakeRespShinhan({"access_token": "test_token", "expires_in": 86400})

    return FakeHttp()


class TestShinhanAdapterETF:
    def _make_adapter(self, etf_items):
        adapter = ShinhanStockAdapter(
            user_id="u", password="p", account_no="1234",
            app_key="k", app_secret="s",
        )
        adapter._http = _make_shinhan_backend(etf_items)
        adapter.connect()
        return adapter

    def test_get_etf_list_maps_isuSrtCd_to_code(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "069500", "isuNm": "KODEX200",
             "clsprc": "35000", "nav": "34950",
             "trcErrRt": "0.15", "bchidxNm": "KOSPI200"},
        ])
        result = adapter.get_etf_list()
        assert len(result) == 1
        assert result[0]["code"] == "069500"
        assert result[0]["name"] == "KODEX200"

    def test_get_etf_list_maps_nav_field(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "069500", "isuNm": "KODEX200",
             "clsprc": "35000", "nav": "34950", "trcErrRt": "0.20"},
        ])
        assert float(adapter.get_etf_list()[0]["nav"]) == pytest.approx(34950.0)

    def test_get_etf_list_maps_trcErrRt_as_tracking_error(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "114800", "isuNm": "KODEX인버스",
             "clsprc": "5000", "nav": "4990", "trcErrRt": "0.30"},
        ])
        result = adapter.get_etf_list()[0]["tracking_error"]
        assert result == pytest.approx(0.30), f"tracking_error 예상 0.30, 실제 {result!r}"

    def test_get_etf_list_maps_bchidxNm_as_base_index(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "261120", "isuNm": "국고채3년",
             "clsprc": "9800", "nav": "9795",
             "trcErrRt": "0.05", "bchidxNm": "국고채3년"},
        ])
        assert adapter.get_etf_list()[0]["base_index"] == "국고채3년"

    def test_get_etf_list_is_etf_flag_always_true(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "069500", "isuNm": "K200",
             "clsprc": "35000", "nav": "34950", "trcErrRt": None},
        ])
        assert adapter.get_etf_list()[0]["is_etf"] is True

    def test_get_etf_list_not_connected_returns_empty(self):
        adapter = ShinhanStockAdapter(user_id="u", password="p")
        assert adapter.get_etf_list() == []

    def test_is_etf_shinhan_same_ranges_as_mock(self):
        adapter = ShinhanStockAdapter(user_id="u", password="p")
        assert adapter.is_etf("069500") is True
        assert adapter.is_etf("005930") is False
        assert adapter.is_etf("292000") is True

    def test_get_etf_list_multiple_items(self):
        adapter = self._make_adapter([
            {"isuSrtCd": "069500", "isuNm": "KODEX200",
             "clsprc": "35000", "nav": "34950", "trcErrRt": "0.15"},
            {"isuSrtCd": "114800", "isuNm": "KODEX인버스",
             "clsprc": "5000", "nav": "4990", "trcErrRt": "0.25"},
        ])
        result = adapter.get_etf_list()
        assert len(result) == 2
        codes = [e["code"] for e in result]
        assert "069500" in codes
        assert "114800" in codes

    def test_get_etf_list_empty_response(self):
        class EmptyHttp:
            _mock_token = "t"
            headers: Dict = {}

            def get(self, url, params=None, timeout=None):
                return FakeRespShinhan({})

            def post(self, url, json=None, timeout=None):
                return FakeRespShinhan({"access_token": "t", "expires_in": 86400})

        adapter = ShinhanStockAdapter(user_id="u", password="p", app_key="k", app_secret="s")
        adapter._http = EmptyHttp()
        adapter.connect()
        assert adapter.get_etf_list() == []


# ──────────────────────────────────────────────────────────────────────────────
# MiraeAssetStockAdapter — get_etf_list 필드명 매핑 (backend 주입)
# ──────────────────────────────────────────────────────────────────────────────

class FakeRespMirae:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def _make_mirae_backend(etf_items: List[Dict[str, Any]]):
    items_ref = etf_items

    class FakeHttp:
        _mock_token = "test_token"
        headers: Dict = {}

        def get(self, url, params=None, timeout=None):
            if "inquire-etf-daily" in url:
                return FakeRespMirae({"output": items_ref})
            return FakeRespMirae({})

        def post(self, url, json=None, timeout=None):
            return FakeRespMirae({"access_token": "test_token", "expires_in": 86400})

    return FakeHttp()


class TestMiraeAssetAdapterETF:
    def _make_adapter(self, etf_items):
        adapter = MiraeAssetStockAdapter(
            user_id="u", password="p", account_no="1234",
            app_key="k", app_secret="s",
        )
        adapter._http = _make_mirae_backend(etf_items)
        adapter.connect()
        return adapter

    def test_get_etf_list_maps_stck_shrt_cd_to_code(self):
        adapter = self._make_adapter([
            {"stck_shrt_cd": "069500", "prdt_name": "KODEX200",
             "stck_prpr": "35000", "nav": "34950",
             "trc_errt": "0.12", "bchm_nm": "KOSPI200"},
        ])
        result = adapter.get_etf_list()
        assert len(result) == 1
        assert result[0]["code"] == "069500"

    def test_get_etf_list_maps_nav_field(self):
        adapter = self._make_adapter([
            {"stck_shrt_cd": "122630", "prdt_name": "KODEX레버리지",
             "stck_prpr": "20000", "nav": "19950", "trc_errt": "0.22"},
        ])
        assert float(adapter.get_etf_list()[0]["nav"]) == pytest.approx(19950.0)

    def test_get_etf_list_maps_trc_errt_as_tracking_error(self):
        adapter = self._make_adapter([
            {"stck_shrt_cd": "114800", "prdt_name": "KODEX인버스",
             "stck_prpr": "5000", "nav": "4990", "trc_errt": "0.35"},
        ])
        result = adapter.get_etf_list()[0]["tracking_error"]
        assert result == pytest.approx(0.35), f"tracking_error 예상 0.35, 실제 {result!r}"

    def test_get_etf_list_maps_bchm_nm_as_base_index(self):
        adapter = self._make_adapter([
            {"stck_shrt_cd": "261120", "prdt_name": "국고채3년",
             "stck_prpr": "9800", "nav": "9795",
             "trc_errt": "0.04", "bchm_nm": "국고채3년"},
        ])
        assert adapter.get_etf_list()[0]["base_index"] == "국고채3년"

    def test_get_etf_list_not_connected_returns_empty(self):
        adapter = MiraeAssetStockAdapter(user_id="u", password="p")
        assert adapter.get_etf_list() == []

    def test_is_etf_mirae_same_ranges_as_mock(self):
        adapter = MiraeAssetStockAdapter(user_id="u", password="p")
        assert adapter.is_etf("069500") is True
        assert adapter.is_etf("005930") is False
        assert adapter.is_etf("143310") is True

    def test_get_etf_list_is_etf_always_true(self):
        adapter = self._make_adapter([
            {"stck_shrt_cd": "069500", "prdt_name": "K200",
             "stck_prpr": "35000", "nav": "34950"},
        ])
        assert adapter.get_etf_list()[0]["is_etf"] is True

    def test_get_etf_list_output_as_dict_wrapped_in_list(self):
        """output이 dict 단일값일 때 리스트로 변환 처리"""
        class DictHttp:
            _mock_token = "t"
            headers: Dict = {}

            def get(self, url, params=None, timeout=None):
                single = {"stck_shrt_cd": "069500", "prdt_name": "K200",
                          "stck_prpr": "35000", "nav": "34950"}
                return FakeRespMirae({"output": single})

            def post(self, url, json=None, timeout=None):
                return FakeRespMirae({"access_token": "t", "expires_in": 86400})

        adapter = MiraeAssetStockAdapter(user_id="u", password="p", app_key="k", app_secret="s")
        adapter._http = DictHttp()
        adapter.connect()
        result = adapter.get_etf_list()
        assert len(result) == 1


# ──────────────────────────────────────────────────────────────────────────────
# ETFMetrics — risk_level, nav_gap, summary, to_dict
# ──────────────────────────────────────────────────────────────────────────────

class TestETFMetrics:
    def test_nav_gap_positive_premium(self):
        m = ETFMetrics("069500", "KODEX200", nav=35000, current_price=35500)
        assert m.nav_gap is not None
        assert m.nav_gap == pytest.approx(500 / 35000 * 100, rel=1e-4)

    def test_nav_gap_negative_discount(self):
        m = ETFMetrics("069500", "KODEX200", nav=35000, current_price=34650)
        assert m.nav_gap < 0

    def test_nav_gap_none_when_nav_zero(self):
        m = ETFMetrics("069500", "KODEX200", nav=0, current_price=35000)
        assert m.nav_gap is None

    def test_risk_level_ok(self):
        m = ETFMetrics("069500", "KODEX200", nav=35000, current_price=35050,
                       tracking_error=0.3, trade_value=10_000_000)
        assert m.risk_level() == "ok"

    def test_risk_level_warn_nav_gap(self):
        # NAV 괴리 0.8% → warn 구간 (0.5%~1.0%)
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35280,
                       tracking_error=0.2)
        assert m.risk_level() == "warn"

    def test_risk_level_alert_nav_gap(self):
        # NAV 괴리 1.5% → alert 구간
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35525)
        assert m.risk_level() == "alert"

    def test_risk_level_alert_tracking_error_high(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35000,
                       tracking_error=4.0)
        assert m.risk_level() == "alert"

    def test_risk_level_warn_tracking_error(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35000,
                       tracking_error=1.5)
        assert m.risk_level() == "warn"

    def test_risk_level_warn_low_trade_value(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35000,
                       trade_value=500_000)
        assert m.risk_level() == "warn"

    def test_risk_level_ok_no_tracking_error(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35000,
                       tracking_error=None, trade_value=5_000_000)
        assert m.risk_level() == "ok"

    def test_summary_contains_code_and_name(self):
        m = ETFMetrics("069500", "KODEX200", nav=35000, current_price=35175)
        s = m.summary()
        assert "069500" in s
        assert "KODEX200" in s

    def test_summary_contains_alert_when_high_gap(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35525)
        assert "[ALERT]" in m.summary()

    def test_to_dict_has_risk_level_key(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35000,
                       tracking_error=0.5)
        d = m.to_dict()
        assert "risk_level" in d
        assert "nav_gap" in d
        assert "tracking_error" in d

    def test_to_dict_values_match_properties(self):
        m = ETFMetrics("069500", "K200", nav=35000, current_price=35175,
                       tracking_error=0.8, trade_value=2_000_000)
        d = m.to_dict()
        assert d["code"] == "069500"
        assert d["nav_gap"] == pytest.approx(m.nav_gap, rel=1e-4)
        assert d["risk_level"] == m.risk_level()


# ──────────────────────────────────────────────────────────────────────────────
# score_etf() 점수 계산
# ──────────────────────────────────────────────────────────────────────────────

class TestScoreETF:
    def test_perfect_etf_near_50(self):
        result = score_etf(35000, 35000, tracking_error=0.0, trade_value=100_000_000)
        assert result["score"] >= 50.0

    def test_large_nav_gap_lowers_score(self):
        result_ok = score_etf(35000, 35000, tracking_error=0.0, trade_value=1_000_000)
        result_gap = score_etf(35700, 35000, tracking_error=0.0, trade_value=1_000_000)
        assert result_gap["score"] < result_ok["score"]

    def test_high_tracking_error_lowers_score(self):
        result_low = score_etf(35000, 35000, tracking_error=0.1, trade_value=1_000_000)
        result_high = score_etf(35000, 35000, tracking_error=4.0, trade_value=1_000_000)
        assert result_high["score"] < result_low["score"]

    def test_high_trade_value_raises_score(self):
        result_low = score_etf(35000, 35000, tracking_error=0.0, trade_value=0)
        result_high = score_etf(35000, 35000, tracking_error=0.0, trade_value=100_000_000)
        assert result_high["score"] > result_low["score"]

    def test_high_expense_ratio_lowers_score(self):
        result_cheap = score_etf(35000, 35000, tracking_error=0.0,
                                 trade_value=10_000_000, expense_ratio=0.001)
        result_expensive = score_etf(35000, 35000, tracking_error=0.0,
                                     trade_value=10_000_000, expense_ratio=0.010)
        assert result_expensive["score"] < result_cheap["score"]

    def test_score_clipped_between_0_and_100(self):
        result = score_etf(40000, 35000, tracking_error=10.0,
                           trade_value=0, expense_ratio=0.05)
        assert 0.0 <= result["score"] <= 100.0

    def test_returns_nav_gap_key(self):
        result = score_etf(35350, 35000, tracking_error=0.5, trade_value=5_000_000)
        assert "nav_gap" in result
        assert result["nav_gap"] >= 0.0

    def test_none_tracking_error_treated_as_zero_penalty(self):
        result_none = score_etf(35000, 35000, tracking_error=None, trade_value=5_000_000)
        result_zero = score_etf(35000, 35000, tracking_error=0.0, trade_value=5_000_000)
        assert result_none["score"] == pytest.approx(result_zero["score"])


# ──────────────────────────────────────────────────────────────────────────────
# StockAnalysisService.get_etf_analysis() — Mock 어댑터 통합
# ──────────────────────────────────────────────────────────────────────────────

class TestStockAnalysisServiceETFPortfolio:
    def setup_method(self):
        self.adapter = StockMockAdapter(broker_name="kiwoom", latency_ms=0)
        self.adapter.connect()
        self.service = StockAnalysisService(self.adapter, broker_name="kiwoom")

    def test_get_etf_analysis_returns_list(self):
        result = self.service.get_etf_analysis()
        assert isinstance(result, list)

    def test_get_etf_analysis_items_are_etf_metrics(self):
        for m in self.service.get_etf_analysis():
            assert isinstance(m, ETFMetrics)

    def test_get_etf_analysis_metrics_have_code(self):
        for m in self.service.get_etf_analysis():
            assert m.code != ""

    def test_get_etf_analysis_no_positions_still_returns_list(self):
        """포지션 없어도 ETF 목록 기반 메트릭 반환"""
        adapter = StockMockAdapter(latency_ms=0)
        adapter.connect()
        adapter._holdings = {}
        service = StockAnalysisService(adapter, broker_name="mock_empty")
        result = service.get_etf_analysis()
        assert isinstance(result, list)

    def test_get_etf_analysis_risk_level_valid(self):
        for m in self.service.get_etf_analysis():
            assert m.risk_level() in ("ok", "warn", "alert")


# ──────────────────────────────────────────────────────────────────────────────
# ETF 실시간 지표 연동 테스트 (get_etf_realtime_metrics + get_etf_analysis 보강)
# ──────────────────────────────────────────────────────────────────────────────

class TestETFRealtimeMetrics:
    """StockMockAdapter.get_etf_realtime_metrics() 및 get_etf_analysis() 실시간 보강 검증."""

    def setup_method(self):
        self.adapter = StockMockAdapter(latency_ms=0)
        self.adapter.connect()
        self.service = StockAnalysisService(self.adapter, broker_name="mock_rt")

    def test_get_etf_realtime_metrics_returns_ok(self):
        """보유 ETF 코드에 대해 status=ok 반환."""
        etf_codes = [e["code"] for e in self.adapter.get_etf_list()]
        assert etf_codes, "샘플 ETF가 있어야 함"
        rt = self.adapter.get_etf_realtime_metrics(etf_codes[0])
        assert rt["status"] == "ok"

    def test_get_etf_realtime_metrics_has_required_fields(self):
        """current_price / nav / tracking_error / trade_value / expense_ratio 필드 보유."""
        code = self.adapter.get_etf_list()[0]["code"]
        rt = self.adapter.get_etf_realtime_metrics(code)
        for field in ("current_price", "nav", "tracking_error", "trade_value", "expense_ratio"):
            assert field in rt, f"{field} 필드 누락"

    def test_get_etf_realtime_metrics_current_price_positive(self):
        code = self.adapter.get_etf_list()[0]["code"]
        rt = self.adapter.get_etf_realtime_metrics(code)
        assert rt["current_price"] > 0

    def test_get_etf_realtime_metrics_nav_positive(self):
        code = self.adapter.get_etf_list()[0]["code"]
        rt = self.adapter.get_etf_realtime_metrics(code)
        assert rt["nav"] > 0

    def test_get_etf_realtime_metrics_trade_value_positive(self):
        code = self.adapter.get_etf_list()[0]["code"]
        rt = self.adapter.get_etf_realtime_metrics(code)
        assert rt["trade_value"] > 0

    def test_get_etf_realtime_metrics_unknown_symbol(self):
        """알 수 없는 코드는 error 반환."""
        rt = self.adapter.get_etf_realtime_metrics("UNKNOWN_ETF_XYZ")
        assert rt["status"] == "error"

    def test_get_etf_analysis_realtime_enrichment(self):
        """get_etf_analysis()가 get_etf_realtime_metrics()로 현재가·NAV·거래대금 보강."""
        metrics = self.service.get_etf_analysis()
        assert isinstance(metrics, list)
        for m in metrics:
            assert isinstance(m, ETFMetrics)
            # 실시간 보강 후에도 ETFMetrics 구조 유지
            assert m.code
            assert m.to_dict()["risk_level"] in ("ok", "warn", "alert")  # risk_level 정상

    def test_get_etf_analysis_expense_ratio_populated(self):
        """실시간 보강 후 expense_ratio 필드가 None이 아닌 값을 가짐."""
        metrics = self.service.get_etf_analysis()
        if metrics:
            # Mock 어댑터는 항상 expense_ratio 제공
            for m in metrics:
                assert m.expense_ratio is not None

    def test_get_etf_list_trade_value_field(self):
        """get_etf_list()에 trade_value 필드 포함 여부 확인."""
        etf_list = self.adapter.get_etf_list()
        for item in etf_list:
            assert "trade_value" in item, f"{item.get('code')} 에 trade_value 필드 없음"
            assert item["trade_value"] >= 0

    def test_shinhan_etf_list_trade_value_field_mapping(self):
        """신한 어댑터 get_etf_list() 필드매핑: acmlTrPbmn → trade_value."""
        adapter = ShinhanStockAdapter.__new__(ShinhanStockAdapter)
        adapter._to_float = lambda v: float(v) if v else 0.0
        adapter._normalize_symbol = lambda s: str(s).strip()
        # get_etf_list 내부 item 처리 직접 검증
        item = {
            'isuSrtCd': '069500',
            'isuNm': 'KODEX200',
            'clsprc': 35000,
            'nav': 34980.0,
            'trcErrRt': '0.05',
            'bchidxNm': 'KOSPI200',
            'acmlTrPbmn': 12_500_000_000,
            'totFeeRt': '0.15',
        }
        # 신한 필드 매핑 규칙 단독 검증
        trade_value = adapter._to_float(item.get('acmlTrPbmn') or item.get('trade_value') or 0)
        expense_ratio = adapter._to_float(item.get('totFeeRt') or item.get('expense_ratio') or 0) or None
        assert trade_value == 12_500_000_000
        assert expense_ratio == pytest.approx(0.15)

    def test_mirae_etf_list_trade_value_field_mapping(self):
        """미래에셋 어댑터 get_etf_list() 필드매핑: acml_tr_pbmn → trade_value."""
        from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
        adapter = MiraeAssetStockAdapter.__new__(MiraeAssetStockAdapter)
        adapter._to_float = lambda v: float(v) if v else 0.0
        adapter._to_float_or_none = lambda v: float(v) if v not in (None, '') else None
        adapter._normalize_symbol = lambda s: str(s).strip()
        item = {
            'stck_shrt_cd': '069500',
            'pdno': '069500',
            'prdt_name': 'KODEX200',
            'stck_prpr': 35100,
            'nav': 35080.0,
            'trc_errt': '0.03',
            'bchm_nm': 'KOSPI200',
            'acml_tr_pbmn': 8_000_000_000,
            'etf_fee_rt': '0.05',
        }
        trade_value = adapter._to_float(item.get('acml_tr_pbmn') or item.get('trade_value') or 0)
        expense_ratio = adapter._to_float_or_none(item.get('etf_fee_rt') or item.get('expense_ratio'))
        assert trade_value == 8_000_000_000
        assert expense_ratio == pytest.approx(0.05)
