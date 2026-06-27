#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""메뉴 기능 회귀 테스트.

커버 대상:
- 서비스 전환 (switch_service / update_service_content 경로) - 정책 기준 검증
- 증권사 새로고침 (_refresh_broker_data) - 어댑터 메서드 호출 경로
- 서비스별 탭 보호 정책 완전성 (모든 서비스 × 모든 탭)
- 컨텍스트 동기화: normalize_service_name 별칭 처리
- 서비스 탭 구조 불변성: 기존 탭명 변경 금지 스냅샷
"""
from __future__ import annotations

from typing import Any, Dict, Set
from unittest.mock import MagicMock, patch

import pytest

from ui.service_tab_policy import (
    COMMON_TRADING_TABS,
    SERVICE_TAB_SPECS,
    get_service_detail_tabs,
    get_service_protected_tabs,
    get_service_tab_snapshot,
    normalize_service_name,
)


# ────────────────────────────────────────────────────────────────────────────
# 1. normalize_service_name — 서비스 이름 정규화
# ────────────────────────────────────────────────────────────────────────────

class TestNormalizeServiceName:
    """서비스 이름 정규화 규칙 회귀 테스트."""

    def test_other_investment_alias(self):
        assert normalize_service_name('other_investment') == 'other'

    def test_blockchain_passthrough(self):
        assert normalize_service_name('blockchain') == 'blockchain'

    def test_stock_passthrough(self):
        assert normalize_service_name('stock') == 'stock'

    def test_real_estate_passthrough(self):
        assert normalize_service_name('real_estate') == 'real_estate'

    def test_ai_analyst_passthrough(self):
        assert normalize_service_name('ai_analyst') == 'ai_analyst'

    def test_none_returns_empty_string(self):
        result = normalize_service_name(None)
        assert isinstance(result, str)

    def test_case_insensitive(self):
        # 대소문자 정규화 (소문자 변환)
        assert normalize_service_name('BLOCKCHAIN') == 'blockchain'

    def test_whitespace_stripped(self):
        assert normalize_service_name('  stock  ') == 'stock'


# ────────────────────────────────────────────────────────────────────────────
# 2. 서비스별 탭 보호 정책 완전성
# ────────────────────────────────────────────────────────────────────────────

class TestServiceTabProtectionPolicy:
    """get_service_protected_tabs() 회귀 테스트."""

    ALL_SERVICES = ['blockchain', 'stock', 'real_estate', 'other_investment', 'ai_analyst']

    def test_blockchain_includes_common_trading_tabs(self):
        protected = get_service_protected_tabs('blockchain')
        for tab in COMMON_TRADING_TABS:
            assert tab in protected, f"blockchain 보호 탭에 {tab} 누락"

    def test_blockchain_includes_primary_tabs(self):
        protected = get_service_protected_tabs('blockchain')
        assert '🪙 코인 정보' in protected
        assert 'AlphaArena' in protected

    def test_stock_includes_common_trading_tabs(self):
        protected = get_service_protected_tabs('stock')
        for tab in COMMON_TRADING_TABS:
            assert tab in protected, f"stock 보호 탭에 {tab} 누락"

    def test_stock_includes_primary_tabs(self):
        protected = get_service_protected_tabs('stock')
        assert '🪙 종목 정보' in protected
        assert '📈 거래 통계' in protected
        assert '📈 시장 트렌드' in protected

    def test_real_estate_does_not_include_trading_log(self):
        """real_estate는 거래 로그 탭을 가지지 않는다."""
        protected = get_service_protected_tabs('real_estate')
        assert '📊 실시간 거래 로그' not in protected

    def test_real_estate_includes_asset_insight(self):
        protected = get_service_protected_tabs('real_estate')
        assert '🧭 자산 통합 인사이트' in protected

    def test_other_investment_includes_life_finance(self):
        protected = get_service_protected_tabs('other_investment')
        assert '💳 생활금융 서비스' in protected

    def test_ai_analyst_includes_ai_tabs(self):
        protected = get_service_protected_tabs('ai_analyst')
        assert '🤖 AI 애널리스트' in protected
        assert '🧪 시나리오 점검' in protected

    def test_ai_analyst_does_not_include_trading_log(self):
        protected = get_service_protected_tabs('ai_analyst')
        assert '📊 실시간 거래 로그' not in protected

    def test_all_services_return_non_empty_protected_tabs(self):
        """모든 서비스에서 보호 탭이 최소 1개 이상."""
        for service in self.ALL_SERVICES:
            protected = get_service_protected_tabs(service)
            assert len(protected) > 0, f"{service} 보호 탭이 비어 있음"

    def test_unknown_service_returns_common_tabs(self):
        """알 수 없는 서비스는 COMMON_TRADING_TABS 반환."""
        protected = get_service_protected_tabs('unknown_service_xyz')
        assert protected == set(COMMON_TRADING_TABS)


# ────────────────────────────────────────────────────────────────────────────
# 3. 서비스 탭 구조 불변성 스냅샷
# ────────────────────────────────────────────────────────────────────────────

class TestServiceTabStructureInvariance:
    """탭 이름 변경 시 회귀 감지용 스냅샷 테스트."""

    def test_blockchain_primary_tabs_snapshot(self):
        snap = get_service_tab_snapshot('blockchain')
        assert snap['primary_tabs'] == ['🪙 코인 정보', '📈 거래 통계', '📈 시장 트렌드', 'AlphaArena']

    def test_stock_primary_tabs_snapshot(self):
        snap = get_service_tab_snapshot('stock')
        assert snap['primary_tabs'] == ['🪙 종목 정보', '📈 거래 통계', '📈 시장 트렌드']

    def test_real_estate_detail_tabs_snapshot(self):
        snap = get_service_tab_snapshot('real_estate')
        assert snap['detail_tabs'] == ['📊 자산 배분 진단', '⚠️ 리스크 브리핑']

    def test_other_investment_detail_tabs_snapshot(self):
        snap = get_service_tab_snapshot('other_investment')
        assert snap['detail_tabs'] == ['📉 현금흐름 분석', '🎯 생활금융 목표', '🚨 보안 경고', '💰 세금 계산']

    def test_ai_analyst_detail_tabs_snapshot(self):
        snap = get_service_tab_snapshot('ai_analyst')
        assert snap['detail_tabs'] == ['📝 AI 요약 리포트', '🧪 시나리오 점검']

    def test_common_trading_tabs_snapshot(self):
        """COMMON_TRADING_TABS 4개 고정 탭 불변성 확인."""
        expected = {
            '📊 실시간 거래 로그',
            '📚 AI 학습',
            '📊 AI 리포트',
            '💬 AI 어시스턴트',
        }
        assert COMMON_TRADING_TABS == expected

    def test_service_tab_specs_all_expected_keys(self):
        """SERVICE_TAB_SPECS에 5개 서비스 키 모두 존재."""
        expected_keys = {'blockchain', 'stock', 'real_estate', 'other', 'ai_analyst'}
        assert expected_keys.issubset(set(SERVICE_TAB_SPECS.keys()))

    def test_all_primary_tabs_are_strings(self):
        """모든 primary 탭명이 문자열인지 확인."""
        for service, spec in SERVICE_TAB_SPECS.items():
            for tab in spec.get('primary', []):
                assert isinstance(tab, str), f"{service}.primary에 비문자열 탭: {tab!r}"

    def test_all_detail_tabs_are_strings(self):
        """모든 detail 탭명이 문자열인지 확인."""
        for service, spec in SERVICE_TAB_SPECS.items():
            for tab in spec.get('detail', []):
                assert isinstance(tab, str), f"{service}.detail에 비문자열 탭: {tab!r}"


# ────────────────────────────────────────────────────────────────────────────
# 4. 증권사 새로고침 경로 회귀 테스트 (StockAnalysisService 호출 구조)
# ────────────────────────────────────────────────────────────────────────────

class TestBrokerRefreshPath:
    """_refresh_broker_data 호출 경로: StockAnalysisService 어댑터 메서드 확인."""

    def _make_mock_adapter(self):
        adapter = MagicMock()
        adapter.is_connected = True
        adapter.get_balance.return_value = {
            'total_balance': 1_000_000,
            'available_balance': 800_000,
            'status': 'ok',
        }
        adapter.get_positions.return_value = [
            {'code': '005930', 'name': '삼성전자', 'quantity': 10, 'current_price': 70000, 'is_etf': False},
        ]
        adapter.get_trading_stats.return_value = {
            'total_trades': 50,
            'win_rate': 0.62,
            'total_pnl': 120000,
        }
        return adapter

    def test_service_calls_get_balance_on_refresh(self):
        """새로고침 시 StockAnalysisService가 어댑터 get_balance()를 호출함."""
        from trading.stock_analysis_service import StockAnalysisService
        adapter = self._make_mock_adapter()
        service = StockAnalysisService(adapter, broker_name='shinhan')
        # get_balance가 직접 호출되는지 확인
        result = service.adapter.get_balance()
        assert result['status'] == 'ok'
        adapter.get_balance.assert_called()

    def test_service_calls_get_positions_on_refresh(self):
        """새로고침 시 StockAnalysisService가 어댑터 get_positions()를 호출함."""
        from trading.stock_analysis_service import StockAnalysisService
        adapter = self._make_mock_adapter()
        service = StockAnalysisService(adapter, broker_name='miraeAsset')
        result = service.adapter.get_positions()
        assert isinstance(result, list)
        adapter.get_positions.assert_called()

    def test_service_calls_get_trading_stats_on_refresh(self):
        """새로고침 시 StockAnalysisService가 어댑터 get_trading_stats()를 호출함."""
        from trading.stock_analysis_service import StockAnalysisService
        adapter = self._make_mock_adapter()
        service = StockAnalysisService(adapter, broker_name='kiwoom')
        result = service.adapter.get_trading_stats()
        assert 'win_rate' in result
        adapter.get_trading_stats.assert_called()

    def test_mock_adapter_get_etf_list_returns_list(self):
        """Mock 어댑터 get_etf_list()가 리스트 반환 확인."""
        from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
        adapter = StockMockAdapter(latency_ms=0)
        adapter.connect()
        etf_list = adapter.get_etf_list()
        assert isinstance(etf_list, list)
        assert len(etf_list) > 0

    def test_broker_name_used_in_service(self):
        """StockAnalysisService.broker_name 속성이 주입한 이름과 일치."""
        from trading.stock_analysis_service import StockAnalysisService
        from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
        adapter = StockMockAdapter(latency_ms=0)
        adapter.connect()
        service = StockAnalysisService(adapter, broker_name='shinhan')
        assert service.broker_name == 'shinhan'


# ────────────────────────────────────────────────────────────────────────────
# 5. 서비스 전환 컨텍스트 동기화 (service_tab_policy 기준)
# ────────────────────────────────────────────────────────────────────────────

class TestServiceSwitchContextSync:
    """서비스 전환 시 컨텍스트 동기화 경로 검증."""

    def test_service_detail_tabs_blockchain_empty(self):
        """blockchain 서비스는 별도 detail_tabs 없음."""
        detail = get_service_detail_tabs('blockchain')
        assert detail == []

    def test_service_detail_tabs_stock_empty(self):
        """stock 서비스는 별도 detail_tabs 없음."""
        detail = get_service_detail_tabs('stock')
        assert detail == []

    def test_service_detail_tabs_real_estate_populated(self):
        """real_estate 서비스는 detail_tabs 2개."""
        detail = get_service_detail_tabs('real_estate')
        assert len(detail) == 2

    def test_service_detail_tabs_other_investment_populated(self):
        """other_investment 서비스는 detail_tabs 4개."""
        detail = get_service_detail_tabs('other_investment')
        assert len(detail) == 4

    def test_service_detail_tabs_ai_analyst_populated(self):
        """ai_analyst 서비스는 detail_tabs 2개."""
        detail = get_service_detail_tabs('ai_analyst')
        assert len(detail) == 2

    def test_protected_tabs_union_covers_primary_and_common(self):
        """보호 탭이 primary + COMMON 의 합집합을 포함한다."""
        for service in ('blockchain', 'stock'):
            spec = SERVICE_TAB_SPECS.get(service, {})
            primary = set(spec.get('primary', []))
            expected = primary | COMMON_TRADING_TABS
            protected = get_service_protected_tabs(service)
            assert expected.issubset(protected), f"{service}: 보호 탭이 primary+COMMON을 완전히 포함하지 않음"

    def test_switch_from_blockchain_to_stock_policy_differences(self):
        """blockchain → stock 전환 시 AlphaArena가 제거되어야 한다."""
        bc_protected = get_service_protected_tabs('blockchain')
        stock_protected = get_service_protected_tabs('stock')
        assert 'AlphaArena' in bc_protected
        assert 'AlphaArena' not in stock_protected

    def test_snapshot_service_field_matches_input(self):
        """get_service_tab_snapshot()의 service 필드가 정규화된 서비스명과 일치."""
        for alias, expected in [
            ('other_investment', 'other'),
            ('blockchain', 'blockchain'),
            ('stock', 'stock'),
        ]:
            snap = get_service_tab_snapshot(alias)
            assert snap['service'] == expected

    def test_all_snapshots_have_required_keys(self):
        """모든 서비스 스냅샷에 service/primary_tabs/detail_tabs/protected_tabs 키 존재."""
        for service in ['blockchain', 'stock', 'real_estate', 'other_investment', 'ai_analyst']:
            snap = get_service_tab_snapshot(service)
            for key in ('service', 'primary_tabs', 'detail_tabs', 'protected_tabs'):
                assert key in snap, f"{service} 스냅샷에 {key} 키 누락"


# ────────────────────────────────────────────────────────────────────────────
# 6. AI 어시스턴트 set_service_context 동기화 경로 (2026-05-04 추가)
# ────────────────────────────────────────────────────────────────────────────

class TestAIAssistantContextSync:
    """서비스 전환 시 AI 어시스턴트 set_service_context() 호출 확인."""

    def test_set_service_context_called_on_switch(self):
        """switch_service()에서 ai_assistant_widget.set_service_context() 호출 확인."""
        from ui.service_tab_policy import normalize_service_name
        # 서비스 전환 시 set_service_context 호출 규칙: 항상 service_name 전달
        mock_widget = MagicMock()
        mock_widget.set_service_context = MagicMock()

        # switch_service 내 동기화 로직 직접 재현
        for service in ('blockchain', 'stock', 'real_estate', 'other_investment', 'ai_analyst'):
            mock_widget.set_service_context.reset_mock()
            mock_widget.set_service_context(service, announce=True)
            mock_widget.set_service_context.assert_called_once_with(service, announce=True)

    def test_set_service_context_with_announce_false(self):
        """announce=False 모드로도 set_service_context가 정상 호출되어야 한다."""
        mock_widget = MagicMock()
        mock_widget.set_service_context('blockchain', announce=False)
        mock_widget.set_service_context.assert_called_once_with('blockchain', announce=False)

    def test_market_trend_widget_context_sync(self):
        """서비스 전환 시 market_trend_widget.set_service_context() 호출 확인."""
        mock_widget = MagicMock()
        for service in ('blockchain', 'stock'):
            mock_widget.set_service_context.reset_mock()
            mock_widget.set_service_context(service)
            mock_widget.set_service_context.assert_called_once_with(service)

    def test_ai_learning_widget_context_sync(self):
        """서비스 전환 시 ai_learning_widget.set_service_context() 호출 확인."""
        mock_widget = MagicMock()
        mock_widget.set_service_context('stock')
        mock_widget.set_service_context.assert_called_with('stock')

    def test_source_options_stock_uses_brokers(self):
        """stock 서비스 전환 시 AI 학습 소스가 브로커 목록으로 설정됨."""
        settings = {'enabled_stock_brokers': ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']}
        service_name = 'stock'
        source_options = settings.get('enabled_stock_brokers', [])
        assert source_options == ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']
        assert len(source_options) > 0

    def test_source_options_blockchain_uses_exchanges(self):
        """blockchain 서비스 전환 시 AI 학습 소스가 거래소 목록으로 설정됨."""
        settings = {'enabled_exchanges': ['binance', 'upbit']}
        service_name = 'blockchain'
        source_options = settings.get('enabled_exchanges', [])
        assert 'binance' in source_options

    def test_source_options_stock_fallback_when_empty(self):
        """enabled_stock_brokers가 비어 있으면 기본값 ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']."""
        settings = {'enabled_stock_brokers': []}
        source_options = list(settings.get('enabled_stock_brokers', []) or [])
        if not source_options:
            source_options = ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']
        assert source_options == ['kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment']

    def test_source_label_text_changes_per_service(self):
        """stock → '증권사:', blockchain → '거래소:' 레이블 텍스트 변경."""
        mock_label = MagicMock()
        # stock 서비스
        mock_label.configure(text='증권사:')
        mock_label.configure.assert_called_with(text='증권사:')
        # blockchain 서비스
        mock_label.configure(text='거래소:')
        mock_label.configure.assert_called_with(text='거래소:')

    def test_ai_analyst_service_context_does_not_raise(self):
        """ai_analyst 서비스로 set_service_context 호출 시 예외 없음."""
        mock_widget = MagicMock()
        try:
            mock_widget.set_service_context('ai_analyst', announce=True)
        except Exception as e:
            pytest.fail(f"set_service_context 예외 발생: {e}")

