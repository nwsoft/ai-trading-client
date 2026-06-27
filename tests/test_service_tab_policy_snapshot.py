#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from ui.service_tab_policy import (
    get_service_protected_tabs,
    get_service_tab_snapshot,
    normalize_service_name,
)


def test_normalize_service_name_alias():
    assert normalize_service_name('other_investment') == 'other'


def test_stock_service_snapshot_contains_expected_tabs():
    snapshot = get_service_tab_snapshot('stock')
    assert snapshot['service'] == 'stock'
    assert snapshot['primary_tabs'] == ['🪙 종목 정보', '📈 거래 통계', '📈 시장 트렌드']
    protected = snapshot['protected_tabs']
    assert '📊 실시간 거래 로그' in protected
    assert '💬 AI 어시스턴트' in protected


def test_real_estate_service_snapshot_contains_detail_tabs():
    snapshot = get_service_tab_snapshot('real_estate')
    assert snapshot['service'] == 'real_estate'
    assert snapshot['detail_tabs'] == ['📊 자산 배분 진단', '⚠️ 리스크 브리핑']
    protected = set(snapshot['protected_tabs'])
    assert '🧭 자산 통합 인사이트' in protected
    assert '📊 자산 배분 진단' in protected


def test_ai_analyst_protected_tabs_do_not_include_trading_common_tabs():
    protected = get_service_protected_tabs('ai_analyst')
    assert '🤖 AI 애널리스트' in protected
    assert '🧪 시나리오 점검' in protected
    assert '📊 실시간 거래 로그' not in protected
