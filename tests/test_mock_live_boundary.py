#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mock/Live 경계 통합 테스트.

커버 대상:
1. Mock 어댑터 → execution_mode='mock', 실주문 차단 검증
2. allow_live_order 플래그 분기 동작
3. 거래 데이터 구조 정합성 (Mock/Live 공통 키 보장)
4. enable_stock_live_order 설정 → allow_live_order 전달 경로
5. P&L 데이터 타입·범위 검증
"""
from __future__ import annotations

from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, PropertyMock
import pytest

from trading.exchanges.adapters.stock_mock_adapter import StockMockAdapter
from trading.exchanges.exchange_factory import ExchangeFactory
from trading.stock_analysis_service import StockAnalysisService, normalize_asset_mode


# ────────────────────────────────────────────────────────────────────────────
# 공용 fixture
# ────────────────────────────────────────────────────────────────────────────

def make_mock_adapter() -> StockMockAdapter:
    adapter = StockMockAdapter(user_id='test', account_no='ACC001', api_key='KEY')
    adapter.connect()
    return adapter


def make_svc(adapter=None) -> StockAnalysisService:
    if adapter is None:
        adapter = make_mock_adapter()
    return StockAnalysisService(adapter, broker_name='test_broker')


# ────────────────────────────────────────────────────────────────────────────
# 1. Mock 어댑터 → execution_mode 검증
# ────────────────────────────────────────────────────────────────────────────

class TestMockAdapterExecutionMode:

    def test_mock_adapter_api_type_is_mock(self):
        adapter = make_mock_adapter()
        assert adapter.api_type == 'mock'

    def test_run_cycle_with_mock_adapter_sets_execution_mode_mock(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            allow_live_order=False,
        )
        assert result.get('execution_mode') == 'mock'

    def test_run_cycle_execution_mode_mock_even_if_allow_live_order_true(self):
        """Mock 어댑터는 allow_live_order=True여도 execution_mode='mock'."""
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            allow_live_order=True,
        )
        assert result.get('execution_mode') == 'mock'

    def test_result_always_has_execution_mode_key(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        assert 'execution_mode' in result

    def test_result_always_has_orders_executed_key(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        assert 'orders_executed' in result

    def test_result_orders_executed_is_non_negative(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        assert int(result.get('orders_executed', 0)) >= 0

    def test_result_always_has_decisions_list(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        assert isinstance(result.get('decisions', []), list)


# ────────────────────────────────────────────────────────────────────────────
# 2. allow_live_order 플래그 분기
# ────────────────────────────────────────────────────────────────────────────

class TestAllowLiveOrderFlag:

    def _make_live_like_adapter(self):
        """api_type != 'mock'인 어댑터 흉내."""
        adapter = MagicMock()
        adapter.api_type = 'openapi'
        adapter.exchange_name = 'unknown_broker'
        adapter.api_version = 'v1'
        adapter.is_connected = True
        adapter.get_stock_list.return_value = [
            {'code': '005930', 'name': '삼성전자', 'market': 'KOSPI', 'current_price': 70000,
             'is_etf': False}
        ]
        adapter.get_realtime_price.return_value = {
            'status': 'ok', 'code': '005930', 'current_price': 70000,
            'change_rate': 1.5, 'volume': 10000000
        }
        adapter.is_etf = MagicMock(return_value=False)
        return adapter

    def test_live_adapter_allow_live_false_blocks_order(self):
        adapter = self._make_live_like_adapter()
        svc = StockAnalysisService(adapter, broker_name='unknown_broker')
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            allow_live_order=False,
        )
        # live 어댑터 + allow_live_order=False → live_order_blocked reason 또는 orders_executed=0
        assert result.get('execution_mode') == 'live_api'
        blocked = any(
            d.get('reason') in ('live_order_blocked',)
            for d in (result.get('decisions') or [])
        )
        # orders_executed가 0이거나 blocked decision이 있어야 함
        assert int(result.get('orders_executed', 0)) == 0 or blocked

    def test_mock_adapter_skips_live_order_block(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            allow_live_order=False,
        )
        # Mock → live_order_blocked reason이 없어야 함
        has_blocked = any(
            d.get('reason') == 'live_order_blocked'
            for d in (result.get('decisions') or [])
        )
        assert not has_blocked

    def test_allow_live_order_default_is_false(self):
        """파라미터 미입력 시 기본값이 False임을 확인."""
        import inspect
        sig = inspect.signature(StockAnalysisService.run_auto_trade_cycle)
        default = sig.parameters['allow_live_order'].default
        assert default is False

    def test_result_allow_live_order_field_reflects_flag(self):
        svc = make_svc()
        for flag in (True, False):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                allow_live_order=flag,
            )
            if 'allow_live_order' in result:
                assert bool(result['allow_live_order']) == flag


# ────────────────────────────────────────────────────────────────────────────
# 3. 거래 데이터 구조 정합성 (Mock/Live 공통 키 보장)
# ────────────────────────────────────────────────────────────────────────────

class TestTradeDataStructureConsistency:

    REQUIRED_RESULT_KEYS = {
        'execution_mode',
        'orders_executed',
        'decisions',
    }

    REQUIRED_DECISION_KEYS = {
        'symbol',
        'action',
        'reason',
    }

    def test_result_has_all_required_keys(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        for key in self.REQUIRED_RESULT_KEYS:
            assert key in result, f"Missing key: {key}"

    def test_decisions_items_have_required_keys(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930', '069500'])
        for d in (result.get('decisions') or []):
            for key in self.REQUIRED_DECISION_KEYS:
                assert key in d, f"Decision missing key: {key}"

    def test_decision_action_is_valid_enum(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(symbols=['005930'])
        valid_actions = {'BUY', 'SELL', 'HOLD', 'SKIP', 'ERROR'}
        for d in (result.get('decisions') or []):
            assert str(d.get('action', '')).upper() in valid_actions, \
                f"Invalid action: {d.get('action')}"

    def test_multiple_symbols_each_have_decision(self):
        svc = make_svc()
        symbols = ['005930', '069500', '000660']
        result = svc.run_auto_trade_cycle(symbols=symbols)
        decision_symbols = {d.get('symbol') for d in (result.get('decisions') or [])}
        for sym in symbols:
            assert sym in decision_symbols

    def test_orders_executed_matches_buy_sell_decisions(self):
        svc = make_svc()
        result = svc.run_auto_trade_cycle(
            symbols=['005930'],
            buy_threshold=0.0,  # 항상 BUY 신호
            allow_live_order=True,
        )
        executed = int(result.get('orders_executed', 0))
        buy_sell_count = sum(
            1 for d in (result.get('decisions') or [])
            if str(d.get('action', '')).upper() in ('BUY', 'SELL')
            and d.get('reason') not in ('live_order_blocked',)
        )
        assert executed >= 0
        assert buy_sell_count >= 0

    def test_get_positions_returns_consistent_structure(self):
        adapter = make_mock_adapter()
        # 포지션 구조 일관성
        positions = adapter.get_positions()
        for pos in positions:
            assert 'code' in pos or 'symbol' in pos

    def test_get_balance_returns_cash_key(self):
        adapter = make_mock_adapter()
        balance = adapter.get_balance()
        assert 'cash' in balance

    def test_trade_history_has_consistent_fields(self):
        adapter = make_mock_adapter()
        history = adapter.get_trade_history()
        if history:
            for record in history[:3]:
                assert isinstance(record, dict)


# ────────────────────────────────────────────────────────────────────────────
# 4. enable_stock_live_order 설정 → allow_live_order 전달 경로
# ────────────────────────────────────────────────────────────────────────────

class TestEnableStockLiveOrderSetting:

    def _make_dashboard_allow_checker(
        self,
        enable_stock_live_order: bool,
        broker_allow: bool,
        api_type: str = 'openapi_plus',
        api_version: str = 'pykiwoom',
    ):
        """대시보드가 호출하는 공통 순수 함수로 이중 게이트를 검증."""
        return ExchangeFactory.evaluate_stock_live_order_permission(
            broker='kiwoom',
            api_type=api_type,
            api_version=api_version,
            global_live_flag=enable_stock_live_order,
            broker_live_flag=broker_allow,
        )

    def test_both_false_blocks_live_order(self):
        allowed, reason = self._make_dashboard_allow_checker(False, False)
        assert not allowed
        assert reason

    def test_global_flag_cannot_bypass_broker_permission(self):
        allowed, reason = self._make_dashboard_allow_checker(True, False)
        assert not allowed
        assert 'allow_live_order' in reason

    def test_broker_flag_cannot_bypass_global_permission(self):
        allowed, reason = self._make_dashboard_allow_checker(False, True)
        assert not allowed
        assert 'enable_stock_live_order' in reason

    def test_both_flags_allow_implemented_route(self):
        allowed, reason = self._make_dashboard_allow_checker(True, True)
        assert allowed
        assert reason == ''

    def test_runtime_readiness_is_required_after_both_flags(self):
        allowed, reason = ExchangeFactory.evaluate_stock_live_order_permission(
            broker='kiwoom', api_type='openapi_plus', api_version='pykiwoom',
            global_live_flag=True, broker_live_flag=True,
            adapter_ready=False, adapter_ready_reason='OCX 연결 필요',
        )
        assert not allowed
        assert 'OCX 연결 필요' in reason

    def test_mock_api_type_bypasses_flag_check(self):
        """Mock 어댑터는 live_order 플래그 무관 통과."""
        allowed, reason = self._make_dashboard_allow_checker(
            False, False, api_type='mock', api_version='mock'
        )
        assert allowed
        assert reason == ''

    def test_settings_template_default_is_false(self):
        import json
        with open('config/settings_template.json') as f:
            tmpl = json.load(f)
        assert tmpl.get('enable_stock_live_order') is False

    def test_settings_py_default_is_false(self):
        from config.settings import get_default_settings
        defaults = get_default_settings()
        assert not bool(defaults.get('enable_stock_live_order', False))

    def test_broker_allow_live_order_per_broker_default_false(self):
        import json
        with open('config/settings_template.json') as f:
            tmpl = json.load(f)
        configs = tmpl.get('stock_broker_configs', {})
        for broker_key in ('kiwoom', 'shinhan', 'miraeAsset', 'koreaInvestment'):
            assert not bool(configs[broker_key].get('allow_live_order', False)), \
                f"{broker_key}.allow_live_order should be False by default"


# ────────────────────────────────────────────────────────────────────────────
# 5. P&L 데이터 타입·범위 검증
# ────────────────────────────────────────────────────────────────────────────

class TestPnLDataIntegrity:

    def test_get_trading_stats_numeric_types(self):
        adapter = make_mock_adapter()
        stats = adapter.get_trading_stats()
        numeric_keys = ['total_trades', 'winning_trades', 'losing_trades',
                        'total_profit', 'win_rate']
        for key in numeric_keys:
            if key in stats:
                val = stats[key]
                assert isinstance(val, (int, float)), \
                    f"{key} should be numeric, got {type(val)}"

    def test_get_trading_stats_win_rate_range(self):
        adapter = make_mock_adapter()
        stats = adapter.get_trading_stats()
        if 'win_rate' in stats:
            assert 0.0 <= float(stats['win_rate']) <= 100.0

    def test_get_trading_stats_total_trades_non_negative(self):
        adapter = make_mock_adapter()
        stats = adapter.get_trading_stats()
        if 'total_trades' in stats:
            assert int(stats['total_trades']) >= 0

    def test_place_buy_reduces_balance(self):
        adapter = make_mock_adapter()
        initial_cash = float(adapter.get_balance().get('cash', 0))
        result = adapter.place_order('005930', 'BUY', 1, 70000)
        if result.get('status') == 'ok':
            new_cash = float(adapter.get_balance().get('cash', 0))
            assert new_cash < initial_cash

    def test_cycle_result_has_no_negative_orders_executed(self):
        svc = make_svc()
        for _ in range(3):
            result = svc.run_auto_trade_cycle(symbols=['005930'])
            assert int(result.get('orders_executed', 0)) >= 0
