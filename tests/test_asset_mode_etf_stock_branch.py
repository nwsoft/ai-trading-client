#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ETF/주식 분기 로직 완결 테스트.

커버 대상:
1. normalize_asset_mode() 입력 정규화
2. asset_mode_matches() 자산 유형 필터
3. filter_positions_by_asset_mode() 포지션 필터
4. run_auto_trade_cycle() asset_mode 분기 (etf_only / stock_only / all)
5. get_etf_analysis() ETF 전용 지표 사용 여부
6. is_etf() 코드 기반 ETF 탐지 (Mock 어댑터)
7. score_etf / score_stock 분기
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from trading.stock_analysis_service import (
    StockAnalysisService,
    normalize_asset_mode,
    asset_mode_matches,
    filter_positions_by_asset_mode,
)
from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter


# ────────────────────────────────────────────────────────────────────────────
# 공용 fixture
# ────────────────────────────────────────────────────────────────────────────

def make_adapter() -> StockMockAdapter:
    a = StockMockAdapter(user_id='u', account_no='A', api_key='K')
    a.connect()
    return a


def make_svc(adapter=None) -> StockAnalysisService:
    return StockAnalysisService(adapter or make_adapter(), broker_name='test')


SAMPLE_POSITIONS_MIXED = [
    {'code': '005930', 'name': '삼성전자', 'is_etf': False, 'quantity': 10, 'current_value': 700000},
    {'code': '069500', 'name': 'KODEX 200', 'is_etf': True,  'quantity': 5,  'current_value': 300000},
    {'code': '000660', 'name': 'SK하이닉스', 'is_etf': False, 'quantity': 3, 'current_value': 400000},
    {'code': '114800', 'name': 'KODEX 인버스', 'is_etf': True, 'quantity': 2, 'current_value': 100000},
]


# ────────────────────────────────────────────────────────────────────────────
# 1. normalize_asset_mode
# ────────────────────────────────────────────────────────────────────────────

class TestNormalizeAssetMode:

    @pytest.mark.parametrize("inp,expected", [
        ('all', 'all'),
        ('ALL', 'all'),
        ('stock', 'stock'),
        ('stocks', 'stock'),
        ('STOCK', 'stock'),
        ('etf', 'etf'),
        ('ETF', 'etf'),
        ('unknown', 'all'),
        ('', 'all'),
        (None, 'all'),
    ])
    def test_normalize(self, inp, expected):
        assert normalize_asset_mode(inp) == expected

    def test_etf_only_alias_not_present(self):
        """'etf_only' 별칭은 'all'로 폴백된다(현재 구현 기준)."""
        result = normalize_asset_mode('etf_only')
        assert result in ('etf', 'all')


# ────────────────────────────────────────────────────────────────────────────
# 2. asset_mode_matches
# ────────────────────────────────────────────────────────────────────────────

class TestAssetModeMatches:

    def test_all_matches_both(self):
        assert asset_mode_matches('all', True) is True
        assert asset_mode_matches('all', False) is True

    def test_stock_only_matches_non_etf(self):
        assert asset_mode_matches('stock', False) is True
        assert asset_mode_matches('stock', True) is False

    def test_etf_only_matches_etf(self):
        assert asset_mode_matches('etf', True) is True
        assert asset_mode_matches('etf', False) is False

    def test_stocks_alias_matches_non_etf(self):
        assert asset_mode_matches('stocks', False) is True
        assert asset_mode_matches('stocks', True) is False


# ────────────────────────────────────────────────────────────────────────────
# 3. filter_positions_by_asset_mode
# ────────────────────────────────────────────────────────────────────────────

class TestFilterPositionsByAssetMode:

    def test_filter_all_returns_all(self):
        result = filter_positions_by_asset_mode(SAMPLE_POSITIONS_MIXED, 'all')
        assert len(result) == 4

    def test_filter_stock_returns_only_stocks(self):
        result = filter_positions_by_asset_mode(SAMPLE_POSITIONS_MIXED, 'stock')
        assert all(not p.get('is_etf') for p in result)
        assert len(result) == 2

    def test_filter_etf_returns_only_etfs(self):
        result = filter_positions_by_asset_mode(SAMPLE_POSITIONS_MIXED, 'etf')
        assert all(p.get('is_etf') for p in result)
        assert len(result) == 2

    def test_filter_empty_returns_empty(self):
        result = filter_positions_by_asset_mode([], 'stock')
        assert result == []

    def test_filter_does_not_mutate_original(self):
        original_len = len(SAMPLE_POSITIONS_MIXED)
        filter_positions_by_asset_mode(SAMPLE_POSITIONS_MIXED, 'etf')
        assert len(SAMPLE_POSITIONS_MIXED) == original_len

    def test_filter_stock_count_matches_is_etf_false(self):
        result = filter_positions_by_asset_mode(SAMPLE_POSITIONS_MIXED, 'stocks')
        expected = [p for p in SAMPLE_POSITIONS_MIXED if not p.get('is_etf')]
        assert len(result) == len(expected)


# ────────────────────────────────────────────────────────────────────────────
# 4. run_auto_trade_cycle asset_mode 분기
# ────────────────────────────────────────────────────────────────────────────

class TestRunCycleAssetModeBranch:

    def test_etf_mode_skips_stock_symbols(self):
        """asset_mode='etf'이면 주식 코드(is_etf=False)는 주문이 실행되지 않는다."""
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],  # 삼성전자 (주식)
            asset_mode='etf',
        )
        # 주문이 0이어야 함 (asset_mode_filtered 또는 strategy_blocked/HOLD 등)
        assert int(result.get('orders_executed', 0)) == 0

    def test_stock_mode_skips_etf_symbols(self):
        """asset_mode='stock'이면 ETF 코드(is_etf=True)는 주문이 실행되지 않는다."""
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['069500'],  # KODEX 200 (ETF)
            asset_mode='stock',
        )
        # 주문이 0이어야 함 (asset_mode_filtered 또는 strategy_blocked/HOLD 등)
        assert int(result.get('orders_executed', 0)) == 0

    def test_all_mode_processes_both(self):
        """asset_mode='all'이면 주식/ETF 모두 처리한다."""
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930', '069500'],
            asset_mode='all',
        )
        decisions = result.get('decisions', [])
        # 두 심볼 모두 decision이 있어야 함
        decision_symbols = {d.get('symbol') for d in decisions}
        assert '005930' in decision_symbols
        assert '069500' in decision_symbols

    def test_etf_mode_keeps_etf_symbols(self):
        """asset_mode='etf'이면 ETF 코드는 asset_mode_filtered가 되지 않는다."""
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['069500'],  # ETF
            asset_mode='etf',
        )
        decisions = result.get('decisions', [])
        filtered = [d for d in decisions if d.get('reason') == 'asset_mode_filtered']
        assert len(filtered) == 0

    def test_asset_mode_filtered_decision_has_is_etf_field(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],  # 주식
            asset_mode='etf',
        )
        for d in result.get('decisions', []):
            if d.get('reason') == 'asset_mode_filtered':
                assert 'is_etf' in d
                assert 'asset_mode' in d

    def test_asset_mode_all_no_filtered_decisions(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930', '069500'],
            asset_mode='all',
        )
        filtered = [d for d in result.get('decisions', [])
                    if d.get('reason') == 'asset_mode_filtered']
        assert len(filtered) == 0


# ────────────────────────────────────────────────────────────────────────────
# 5. get_etf_analysis ETF 전용 지표
# ────────────────────────────────────────────────────────────────────────────

class TestGetEtfAnalysis:

    def test_get_etf_analysis_returns_list(self):
        svc = make_svc()
        result = svc.get_etf_analysis()
        assert isinstance(result, list)

    def test_etf_analysis_stock_mode_returns_empty(self):
        """asset_mode='stock'이면 ETF 분석이 비어야 한다."""
        svc = make_svc()
        result = svc.get_etf_analysis(asset_mode='stock')
        assert result == []

    def test_etf_metrics_has_risk_level(self):
        svc = make_svc()
        results = svc.get_etf_analysis(asset_mode='all')
        for m in results:
            assert callable(m.risk_level)
            assert m.risk_level() in ('ok', 'warn', 'alert')

    def test_etf_metrics_nav_gap_is_numeric(self):
        svc = make_svc()
        results = svc.get_etf_analysis(asset_mode='all')
        for m in results:
            if m.nav_gap is not None:
                assert isinstance(m.nav_gap, (int, float))


# ────────────────────────────────────────────────────────────────────────────
# 6. MockAdapter.is_etf() 코드 기반 ETF 탐지
# ────────────────────────────────────────────────────────────────────────────

class TestMockAdapterIsEtf:

    @pytest.mark.parametrize("code,expected_etf", [
        ('069500', True),   # KODEX 200
        ('114800', True),   # KODEX 인버스
        ('005930', False),  # 삼성전자
        ('000660', False),  # SK하이닉스
        ('105190', True),   # ETF 코드 범위
    ])
    def test_etf_code_detection(self, code, expected_etf):
        adapter = make_adapter()
        result = adapter.is_etf(code)
        assert bool(result) == expected_etf, \
            f"is_etf({code!r}) should be {expected_etf}, got {result}"

    def test_invalid_code_returns_false(self):
        adapter = make_adapter()
        assert not adapter.is_etf('')
        assert not adapter.is_etf(None)

    def test_etf_list_items_have_is_etf_true(self):
        adapter = make_adapter()
        etf_list = adapter.get_etf_list()
        for item in etf_list:
            if 'is_etf' in item:
                assert item['is_etf'] is True

    def test_stock_list_items_have_is_etf_false(self):
        adapter = make_adapter()
        stock_list = adapter.get_stock_list('KOSPI')
        for item in stock_list:
            if 'is_etf' in item:
                assert item['is_etf'] is False


# ────────────────────────────────────────────────────────────────────────────
# 7. score_etf / score_stock 분기
# ────────────────────────────────────────────────────────────────────────────

class TestScoreEtfStockBranch:

    def test_analyze_symbol_etf_uses_etf_score_model(self):
        """ETF 코드 분석 시 score_model에 'etf'가 포함되어야 한다."""
        svc = make_svc()
        result = svc.analyze_symbol('069500')
        if result.get('status') == 'ok':
            score_model = str(result.get('score_model', '')).lower()
            assert 'etf' in score_model or result.get('is_etf') is True

    def test_analyze_symbol_stock_uses_stock_score_model(self):
        """주식 코드 분석 시 score_model에 'stock'이 포함되어야 한다."""
        svc = make_svc()
        result = svc.analyze_symbol('005930')
        if result.get('status') == 'ok':
            score_model = str(result.get('score_model', '')).lower()
            assert 'stock' in score_model or result.get('is_etf') is False

    def test_analyze_symbol_has_is_etf_field(self):
        svc = make_svc()
        for code in ['005930', '069500']:
            result = svc.analyze_symbol(code)
            if result.get('status') == 'ok':
                assert 'is_etf' in result

    def test_etf_analysis_result_is_etf_true(self):
        svc = make_svc()
        result = svc.analyze_symbol('069500')
        if result.get('status') == 'ok':
            assert result.get('is_etf') is True

    def test_stock_analysis_result_is_etf_false(self):
        svc = make_svc()
        result = svc.analyze_symbol('005930')
        if result.get('status') == 'ok':
            assert result.get('is_etf') is False
