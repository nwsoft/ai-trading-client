#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주식/ETF 분석 서비스 테스트
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# 유틸 / 순수 함수 테스트
# ---------------------------------------------------------------------------

class TestMarketSession:
    def test_import(self):
        from trading.stock_analysis_service import get_market_session
        session = get_market_session()
        assert session in ('pre', 'open', 'post', 'closed')


class TestETFMetrics:
    def _make_etf(self, **kwargs):
        from trading.stock_analysis_service import ETFMetrics
        defaults = dict(
            code='069500',
            name='KODEX 200',
            nav=95000.0,
            current_price=95000.0,
            tracking_error=0.3,
            trade_value=5_000_000_000.0,
            base_index='KOSPI200',
        )
        defaults.update(kwargs)
        return ETFMetrics(**defaults)

    def test_nav_gap_zero(self):
        m = self._make_etf(nav=100.0, current_price=100.0)
        assert m.nav_gap == pytest.approx(0.0)

    def test_nav_gap_positive(self):
        m = self._make_etf(nav=100.0, current_price=101.0)
        assert m.nav_gap == pytest.approx(1.0)

    def test_nav_gap_none_when_nav_zero(self):
        m = self._make_etf(nav=0.0, current_price=100.0)
        assert m.nav_gap is None

    def test_risk_ok(self):
        m = self._make_etf(nav=100.0, current_price=100.2, tracking_error=0.3)
        assert m.risk_level() == 'ok'

    def test_risk_warn_nav_gap(self):
        m = self._make_etf(nav=100.0, current_price=100.7, tracking_error=0.3)
        assert m.risk_level() == 'warn'

    def test_risk_alert_nav_gap(self):
        m = self._make_etf(nav=100.0, current_price=101.5, tracking_error=0.3)
        assert m.risk_level() == 'alert'

    def test_risk_alert_tracking_error(self):
        m = self._make_etf(nav=100.0, current_price=100.0, tracking_error=3.5)
        assert m.risk_level() == 'alert'

    def test_risk_warn_low_trade_value(self):
        m = self._make_etf(nav=100.0, current_price=100.0, tracking_error=0.3, trade_value=500_000)
        assert m.risk_level() == 'warn'

    def test_summary_contains_code(self):
        m = self._make_etf()
        assert '069500' in m.summary()

    def test_to_dict_keys(self):
        m = self._make_etf()
        d = m.to_dict()
        for key in ('code', 'name', 'nav', 'current_price', 'nav_gap', 'tracking_error', 'risk_level'):
            assert key in d, f"key '{key}' missing from to_dict"


class TestScoreStock:
    def test_import(self):
        from trading.stock_analysis_service import score_stock
        result = score_stock(10000, 10000, 1000)
        assert 'score' in result
        assert 0 <= result['score'] <= 100

    def test_positive_momentum(self):
        from trading.stock_analysis_service import score_stock
        result = score_stock(11000, 10000, 5000, avg_volume=2000)
        result_flat = score_stock(10000, 10000, 5000, avg_volume=2000)
        assert result['score'] > result_flat['score']

    def test_negative_pnl_lowers_score(self):
        from trading.stock_analysis_service import score_stock
        low = score_stock(10000, 10000, 1000, pnl_rate=-20.0)
        high = score_stock(10000, 10000, 1000, pnl_rate=0.0)
        assert low['score'] < high['score']

    def test_score_clamped(self):
        from trading.stock_analysis_service import score_stock
        result = score_stock(20000, 10000, 999_999, avg_volume=1, pnl_rate=100.0)
        assert result['score'] <= 100.0

        result_low = score_stock(100, 10000, 0, avg_volume=999_999, pnl_rate=-100.0)
        assert result_low['score'] >= 0.0


class TestStockExitPolicy:
    def test_take_profit_triggers_exit(self):
        from trading.stock_exit_policy import evaluate_stock_position_exit

        result = evaluate_stock_position_exit(
            position={'code': '005930', 'pnl_rate': 6.1, 'is_etf': False},
            analysis_result={'signal': 'HOLD', 'score': 65, 'momentum': 0.2, 'is_etf': False},
            policy={'enable_exit_policy': True, 'take_profit_percent': 5.0},
        )

        assert result['should_exit'] is True
        assert 'take_profit' in result['reason']

    def test_signal_exit_triggers_exit(self):
        from trading.stock_exit_policy import evaluate_stock_position_exit

        result = evaluate_stock_position_exit(
            position={'code': '005930', 'pnl_rate': 1.2, 'is_etf': False},
            analysis_result={'signal': 'SELL', 'score': 20, 'momentum': -1.0, 'is_etf': False},
            policy={'enable_exit_policy': True, 'use_signal_exit': True},
        )

        assert result['should_exit'] is True
        assert 'signal_exit' in result['reason']


class TestSummarizePortfolio:
    def _make_positions(self):
        return [
            {'code': '005930', 'name': '삼성전자', 'quantity': 10, 'avg_price': 70000,
             'current_price': 72000, 'eval_amount': 720_000, 'pnl': 20_000, 'pnl_rate': 2.8, 'is_etf': False},
            {'code': '069500', 'name': 'KODEX 200', 'quantity': 5, 'avg_price': 30000,
             'current_price': 28000, 'eval_amount': 140_000, 'pnl': -10_000, 'pnl_rate': -6.7, 'is_etf': True},
        ]

    def test_basic(self):
        from trading.stock_analysis_service import summarize_portfolio
        result = summarize_portfolio(self._make_positions())
        assert result['count'] == 2
        assert result['etf_count'] == 1
        assert result['stock_count'] == 1

    def test_total_eval(self):
        from trading.stock_analysis_service import summarize_portfolio
        result = summarize_portfolio(self._make_positions())
        assert result['total_eval'] == pytest.approx(860_000)

    def test_risk_items(self):
        from trading.stock_analysis_service import summarize_portfolio
        result = summarize_portfolio(self._make_positions())
        # KODEX 200 pnl_rate=-6.7 → 위험 종목
        assert any(r['code'] == '069500' for r in result['risk_items'])

    def test_empty(self):
        from trading.stock_analysis_service import summarize_portfolio
        result = summarize_portfolio([])
        assert result['count'] == 0
        assert result['total_eval'] == 0.0


class TestAssetModeHelpers:
    def test_normalize_asset_mode(self):
        from trading.stock_analysis_service import normalize_asset_mode

        assert normalize_asset_mode('stock') == 'stock'
        assert normalize_asset_mode('stocks') == 'stock'
        assert normalize_asset_mode('ETF') == 'etf'
        assert normalize_asset_mode('unexpected') == 'all'

    def test_filter_positions_by_asset_mode(self):
        from trading.stock_analysis_service import filter_positions_by_asset_mode

        positions = [
            {'code': '005930', 'is_etf': False},
            {'code': '069500', 'is_etf': True},
        ]

        assert [p['code'] for p in filter_positions_by_asset_mode(positions, 'stock')] == ['005930']
        assert [p['code'] for p in filter_positions_by_asset_mode(positions, 'etf')] == ['069500']
        assert len(filter_positions_by_asset_mode(positions, 'all')) == 2


# ---------------------------------------------------------------------------
# StockAnalysisService 통합 테스트 (Mock 어댑터)
# ---------------------------------------------------------------------------

def _make_mock_adapter():
    adapter = MagicMock()
    adapter.broker_name = 'mock'
    adapter.is_connected = True
    adapter.get_balance.return_value = {
        'cash': 1_000_000,
        'stock_eval': 500_000,
        'total_assets': 1_500_000,
        'profit_loss': 50_000,
        'profit_rate': 3.45,
        'account_no': '1234567890',
        'status': 'ok',
    }
    adapter.get_positions.return_value = [
        {'code': '005930', 'name': '삼성전자', 'quantity': 5,
         'avg_price': 70000, 'current_price': 72000,
         'eval_amount': 360_000, 'pnl': 10_000, 'pnl_rate': 2.8, 'is_etf': False},
        {'code': '069500', 'name': 'KODEX 200', 'quantity': 3,
         'avg_price': 30000, 'current_price': 28000,
         'eval_amount': 84_000, 'pnl': -6_000, 'pnl_rate': -6.7, 'is_etf': True},
    ]
    adapter.get_etf_list.return_value = [
        {'code': '069500', 'name': 'KODEX 200', 'market': 'ETF',
         'nav': 28500.0, 'tracking_error': 0.4, 'trade_value': 2_000_000_000},
    ]
    adapter.get_trading_stats.return_value = {
        'broker': 'mock',
        'total_trades': 20,
        'buy_count': 12,
        'sell_count': 8,
        'today_trades': 3,
        'open_orders': 1,
        'realized_pnl': 50_000,
        'status': 'ok',
    }
    adapter.get_today_trades.return_value = [
        {'order_id': 'O1', 'symbol': '005930', 'side': 'BUY', 'quantity': 2, 'filled_price': 71000},
    ]
    adapter.get_open_orders.return_value = [
        {'order_id': 'O2', 'symbol': '069500', 'side': 'BUY', 'quantity': 1, 'price': 28000},
    ]
    adapter.get_trade_history.return_value = []
    adapter.get_stock_info.return_value = {
        'code': '005930', 'name': '삼성전자', 'market': 'KOSPI',
        'current_price': 72000, 'prev_close': 71000,
        'change_rate': 1.41, 'volume': 12_000_000, 'is_etf': False, 'status': 'ok',
    }
    adapter.get_realtime_price.return_value = {
        'code': '005930', 'current_price': 72000,
        'change_rate': 1.41, 'volume': 12_000_000, 'status': 'ok',
    }
    adapter.is_etf = lambda code: code == '069500'
    return adapter


class TestStockAnalysisService:
    @pytest.fixture
    def svc(self):
        from trading.stock_analysis_service import StockAnalysisService
        recorder = MagicMock()
        recorder.execute_query.return_value = []
        recorder.insert_trade_log.return_value = 1
        return StockAnalysisService(_make_mock_adapter(), broker_name='mock', recorder=recorder)

    def test_portfolio_summary(self, svc):
        result = svc.get_portfolio_summary()
        assert result['count'] == 2
        assert result['etf_count'] == 1
        assert result['cash'] == pytest.approx(1_000_000)

    def test_etf_analysis(self, svc):
        metrics_list = svc.get_etf_analysis()
        assert len(metrics_list) == 1
        m = metrics_list[0]
        assert m.code == '069500'
        # nav=28500, current_price=28000 → 괴리율 음수
        assert m.nav_gap is not None
        assert m.nav_gap < 0

    def test_trade_summary(self, svc):
        result = svc.get_trade_summary()
        assert result['open_orders_count'] == 1
        assert result['today_count'] == 1
        assert result['realized_pnl'] == pytest.approx(50_000)

    def test_build_ai_context(self, svc):
        ctx = svc.build_ai_context()
        assert 'mock' in ctx.lower() or 'MOCK' in ctx
        assert '보유종목' in ctx
        assert 'ETF' in ctx or 'KODEX' in ctx

    def test_build_ai_context_stock_mode(self, svc):
        ctx = svc.build_ai_context(asset_mode='stock')
        assert '현재 사용자 보기 모드: 주식만' in ctx
        assert 'ETF 0개' in ctx

    def test_build_ai_context_etf_mode(self, svc):
        ctx = svc.build_ai_context(asset_mode='etf')
        assert '현재 사용자 보기 모드: ETF만' in ctx
        assert '[보유 ETF 분석]' in ctx

    def test_analyze_symbol(self, svc):
        result = svc.analyze_symbol('005930')
        assert result['status'] == 'ok'
        assert result['name'] == '삼성전자'
        assert 0 <= result['score'] <= 100
        assert result['analysis_type'] == 'stock'
        assert result['score_model'].startswith('score_stock')  # 컴포넌트 접미사(+ma+rsi+...) 포함 가능
        assert '주식 분석' in result['reasoning']

    def test_analyze_symbol_etf(self, svc):
        svc.adapter.get_stock_info.return_value = {
            'code': '069500', 'name': 'KODEX 200', 'market': 'ETF',
            'current_price': 28000, 'prev_close': 28500,
            'change_rate': -1.75, 'volume': 3_000_000,
            'is_etf': True, 'nav': 28500.0, 'tracking_error': 0.4,
            'status': 'ok',
        }
        svc.adapter.get_realtime_price.return_value = {
            'code': '069500', 'current_price': 28000,
            'change_rate': -1.75, 'volume': 3_000_000, 'status': 'ok',
        }
        result = svc.analyze_symbol('069500')
        assert result['is_etf'] is True
        assert 'etf' in result
        assert result['etf']['code'] == '069500'
        assert result['analysis_type'] == 'etf'
        assert result['score_model'].startswith('score_etf')  # 컴포넌트 접미사(+regime+...) 포함 가능
        assert 'ETF 분석' in result['reasoning']
        assert 'NAV괴리' in result['reasoning']

    def test_evaluate_trade_signal_thresholds(self, svc):
        buy = svc.evaluate_trade_signal({'score': 75, 'momentum': 1.2}, buy_threshold=70, sell_threshold=30)
        sell = svc.evaluate_trade_signal({'score': 25, 'momentum': -0.5}, buy_threshold=70, sell_threshold=30)
        hold = svc.evaluate_trade_signal({'score': 55, 'momentum': 0.1}, buy_threshold=70, sell_threshold=30)

        assert buy == 'BUY'
        assert sell == 'SELL'
        assert hold == 'HOLD'

    def test_evaluate_trade_signal_etf_alert_is_sell(self, svc):
        """ETF: NAV 괴리 alert 수준이면 위험하므로 SELL 신호."""
        signal = svc.evaluate_trade_signal(
            {'is_etf': True, 'etf_risk': 'alert', 'score': 80},
            buy_threshold=70,
        )
        assert signal == 'SELL'

    def test_evaluate_trade_signal_etf_ok_high_score_is_buy(self, svc):
        """ETF: 위험 없고 점수 충분하면 BUY 신호."""
        signal = svc.evaluate_trade_signal(
            {'is_etf': True, 'etf_risk': 'ok', 'score': 75},
            buy_threshold=70,
        )
        assert signal == 'BUY'

    def test_evaluate_trade_signal_etf_warn_is_hold(self, svc):
        """ETF: warn 수준이면 HOLD 유지."""
        signal = svc.evaluate_trade_signal(
            {'is_etf': True, 'etf_risk': 'warn', 'score': 75},
            buy_threshold=70,
        )
        assert signal == 'HOLD'

    # regime 감지 결과와 ProfitabilityValidator 기본 활성화로 인해
    # 개별 가드 도달 테스트는 analyze_symbol·get_market_regime 을 명시적으로 제어한다.
    _MOCK_ANALYSIS_BUY = {
        'status': 'ok', 'symbol': '005930', 'name': '삼성전자',
        'score': 80, 'is_etf': False, 'signal': 'BUY',
        'momentum': 1.0, 'analysis_type': 'stock',
        'score_model': 'score_stock+ma+rsi+flow+regime+feedback',
        'reasoning': '주식 분석',
        'current_price': 72000,
    }

    def test_run_auto_trade_cycle_executes_mock_buy(self, svc):
        svc.adapter.api_type = 'mock'
        svc.adapter.place_order.return_value = {
            'status': 'success',
            'order_id': 'AUTO-1',
            'execution_mode': 'mock',
            'success': True,
        }

        # volatile 레짐 → effective_buy_threshold=50(floor). score=80 으로 명시 제어
        # ProfitabilityValidator 기본 활성(거래 0건 < min_trades=20) 차단 방지
        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='all',
                max_orders=1,
                allow_live_order=False,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={'profitability_validation': {'enabled': False}},
            )

        assert result['status'] == 'ok'
        assert result['orders_executed'] == 1
        assert result['decisions'][0]['action'] == 'BUY'
        assert result['decisions'][0]['success'] is True

    def test_run_auto_trade_cycle_blocks_live_without_flag(self, svc):
        svc.adapter.api_type = 'openapi'

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='all',
                max_orders=1,
                allow_live_order=False,
                auto_risk_policy={'profitability_validation': {'enabled': False}},
            )

        assert result['execution_mode'] == 'live_api'
        assert result['orders_executed'] == 0
        assert result['decisions'][0]['reason'] == 'live_order_blocked'

    def test_run_auto_trade_cycle_blocks_by_guardrails(self, svc):
        svc.adapter.api_type = 'mock'

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='all',
                max_orders=1,
                allow_live_order=True,
                guardrails={
                    'enabled': True,
                    'allow_market_order': False,
                },
                auto_risk_policy={'profitability_validation': {'enabled': False}},
            )

        assert result['status'] == 'ok'
        assert result['orders_executed'] == 0
        assert result['decisions'][0]['reason'] == 'guardrail_blocked'

    def test_run_auto_trade_cycle_blocks_by_daily_loss_guard(self, svc):
        svc.adapter.api_type = 'mock'
        svc.adapter.get_trading_stats.return_value = {
            'broker': 'mock',
            'total_trades': 20,
            'buy_count': 12,
            'sell_count': 8,
            'today_trades': 3,
            'open_orders': 1,
            'realized_pnl': -120_000,
            'status': 'ok',
        }

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='all',
                max_orders=1,
                allow_live_order=True,
                auto_risk_policy={
                    'profitability_validation': {'enabled': False},  # 수익성 검증 우선 차단 방지
                    'risk_guard_enabled': True,
                    'daily_max_loss': 50_000,
                    'max_consecutive_losses': 3,
                    'cooldown_sec_per_symbol': 0,
                },
            )

        assert result['orders_executed'] == 0
        assert result['decisions'][0]['reason'] == 'auto_risk_blocked'

    def test_run_auto_trade_cycle_blocks_by_consecutive_losses_guard(self, svc):
        svc.adapter.api_type = 'mock'
        svc.adapter.get_trading_stats.return_value = {
            'broker': 'mock',
            'total_trades': 3,
            'buy_count': 2,
            'sell_count': 1,
            'today_trades': 3,
            'open_orders': 0,
            'realized_pnl': 0,
            'status': 'ok',
        }
        svc.adapter.get_trade_history.return_value = [
            {'symbol': '005930', 'side': 'SELL', 'quantity': 1, 'filled_price': 70000, 'pnl': -1000, 'timestamp': '2026-04-29T09:01:00'},
            {'symbol': '000660', 'side': 'SELL', 'quantity': 1, 'filled_price': 200000, 'pnl': -2000, 'timestamp': '2026-04-29T09:03:00'},
            {'symbol': '005930', 'side': 'SELL', 'quantity': 1, 'filled_price': 70500, 'pnl': -3000, 'timestamp': '2026-04-29T09:05:00'},
        ]
        svc.adapter.get_today_trades.return_value = []

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='all',
                max_orders=1,
                allow_live_order=True,
                auto_risk_policy={
                    'profitability_validation': {'enabled': False},  # 수익성 검증 우선 차단 방지
                    'risk_guard_enabled': True,
                    'daily_max_loss': 500_000,
                    'max_consecutive_losses': 3,
                    'cooldown_sec_per_symbol': 0,
                },
            )

        assert result['orders_executed'] == 0
        assert result['decisions'][0]['reason'] == 'auto_risk_blocked'

    def test_run_auto_trade_cycle_executes_exit_policy_sell(self, svc):
        svc.adapter.api_type = 'mock'
        svc.adapter.place_order.return_value = {
            'status': 'success',
            'order_id': 'EXIT-1',
            'execution_mode': 'mock',
            'success': True,
        }
        svc.adapter.get_positions.return_value = [
            {
                'code': '005930',
                'name': '삼성전자',
                'quantity': 3,
                'avg_price': 70000,
                'current_price': 74200,
                'eval_amount': 222600,
                'pnl': 12600,
                'pnl_rate': 6.0,
                'is_etf': False,
            }
        ]

        result = svc.run_auto_trade_cycle(
            symbols=[],
            quantity=1,
            order_type='MARKET',
            buy_threshold=70,
            sell_threshold=30,
            asset_mode='all',
            max_orders=1,
            allow_live_order=True,
            exit_policy={
                'enable_exit_policy': True,
                'take_profit_percent': 5.0,
                'stop_loss_percent': 8.0,
                'use_signal_exit': False,
            },
        )

        assert result['orders_executed'] == 1
        assert result['exit_orders_executed'] == 1
        assert result['decisions'][0]['reason'] == 'exit_policy_triggered'

    def test_error_adapter_returns_empty(self, svc):
        svc.adapter.get_balance.side_effect = Exception('연결 실패')
        result = svc.get_portfolio_summary()
        # 오류 발생 시에도 크래시 없이 error 키 반환
        assert 'error' in result or result.get('count', 0) == 0

    def test_emits_analysis_logs(self, svc, monkeypatch):
        from trading import stock_analysis_service as sas

        captured = []

        def _fake_log_event(category, message, **kwargs):
            captured.append((category, message, kwargs))

        monkeypatch.setattr(sas, 'log_event', _fake_log_event)

        # monkeypatch 이후 새로운 인스턴스 생성 필요
        recorder = MagicMock()
        recorder.execute_query.return_value = []
        recorder.insert_trade_log.return_value = 1
        fresh = sas.StockAnalysisService(_make_mock_adapter(), broker_name='mock', recorder=recorder)
        fresh.get_portfolio_summary()
        fresh.get_etf_analysis()
        fresh.get_trade_summary()
        fresh.analyze_symbol('005930')

        assert captured, '분석 로그가 기록되어야 함'
        joined = '\n'.join(m for _, m, _ in captured)
        assert 'portfolio_summary' in joined
        assert 'etf_analysis' in joined
        assert 'trade_summary' in joined
        assert 'analyze_symbol' in joined

    def test_persists_xai_and_analysis_with_recorder(self):
        from trading.stock_analysis_service import StockAnalysisService

        adapter = _make_mock_adapter()
        recorder = MagicMock()
        recorder.execute_query.return_value = []
        recorder.insert_trade_log.return_value = 1
        svc = StockAnalysisService(adapter, broker_name='mock', recorder=recorder)

        svc.get_trade_summary()
        svc.analyze_symbol('005930')
        svc.build_ai_context()

        assert recorder.save_ai_decision.call_count >= 2
        assert recorder.insert_analysis_log.call_count >= 1

    def test_get_recorder_syncs_adapter_recorder_exchange(self):
        from trading.stock_analysis_service import StockAnalysisService

        adapter = _make_mock_adapter()
        adapter.recorder = MagicMock()
        adapter.recorder.exchange = 'binance'

        svc = StockAnalysisService(adapter, broker_name='kiwoom')
        recorder = svc._get_recorder()

        assert recorder is adapter.recorder
        assert recorder.exchange == 'kiwoom'

    def test_get_recorder_syncs_injected_recorder_exchange(self):
        from trading.stock_analysis_service import StockAnalysisService

        adapter = _make_mock_adapter()
        injected = MagicMock()
        injected.exchange = 'binance'

        svc = StockAnalysisService(adapter, broker_name='kiwoom', recorder=injected)
        recorder = svc._get_recorder()

        assert recorder is injected
        assert recorder.exchange == 'kiwoom'

    # ------------------------------------------------------------------
    # ETF 자동매매 시나리오 테스트
    # ------------------------------------------------------------------

    _MOCK_ANALYSIS_ETF_ALERT = {
        'status': 'ok', 'symbol': '069500', 'name': 'KODEX 200',
        'score': 20, 'is_etf': True, 'signal': 'SELL',
        'etf_risk': 'alert', 'etf': {'code': '069500', 'nav_gap': 1.8, 'risk_level': 'alert'},
        'momentum': -0.8, 'analysis_type': 'etf',
        'score_model': 'score_etf+regime',
        'reasoning': 'ETF 분석: NAV괴리 1.8%',
        'current_price': 27000,
    }

    _MOCK_ANALYSIS_ETF_BUY = {
        'status': 'ok', 'symbol': '069500', 'name': 'KODEX 200',
        'score': 78, 'is_etf': True, 'signal': 'BUY',
        'etf_risk': 'ok', 'etf': {'code': '069500', 'nav_gap': 0.1, 'risk_level': 'ok'},
        'momentum': 0.9, 'analysis_type': 'etf',
        'score_model': 'score_etf+regime',
        'reasoning': 'ETF 분석: ok',
        'current_price': 28500,
    }

    def test_run_auto_trade_cycle_etf_alert_triggers_sell(self, svc):
        """ETF alert(NAV 괴리 과대) → SELL 주문 실행."""
        svc.adapter.api_type = 'mock'
        svc.adapter.place_order.return_value = {
            'status': 'success', 'order_id': 'ETF-SELL-1',
            'execution_mode': 'mock', 'success': True,
        }
        svc.adapter.get_positions.return_value = [
            {
                'code': '069500', 'name': 'KODEX 200', 'quantity': 3,
                'avg_price': 30000, 'current_price': 27000,
                'eval_amount': 81000, 'pnl': -9000, 'pnl_rate': -10.0,
                'is_etf': True,
            }
        ]

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_ETF_ALERT)):
            result = svc.run_auto_trade_cycle(
                symbols=['069500'],
                quantity=3,
                order_type='MARKET',
                buy_threshold=70,
                sell_threshold=30,
                asset_mode='etf',
                max_orders=1,
                allow_live_order=True,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={
                    'profitability_validation': {'enabled': False},
                    'strategy_engine': {'enabled': False},  # 전략 엔진 비활성화 — alert SELL 경로 직접 검증
                },
            )

        assert result['status'] == 'ok'
        assert result['orders_executed'] >= 1
        sell_decisions = [d for d in result['decisions'] if d.get('action') == 'SELL']
        assert len(sell_decisions) >= 1

    def test_run_auto_trade_cycle_etf_buy_signal(self, svc):
        """ETF ok 수준 + 고점수 → BUY 주문 실행."""
        svc.adapter.api_type = 'mock'
        svc.adapter.place_order.return_value = {
            'status': 'success', 'order_id': 'ETF-BUY-1',
            'execution_mode': 'mock', 'success': True,
        }

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_ETF_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['069500'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=70,
                sell_threshold=30,
                asset_mode='etf',
                max_orders=1,
                allow_live_order=False,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={'profitability_validation': {'enabled': False}},
            )

        assert result['status'] == 'ok'
        buy_decisions = [d for d in result['decisions'] if d.get('action') == 'BUY']
        assert len(buy_decisions) >= 1

    def test_run_auto_trade_cycle_etf_mode_skips_non_etf(self, svc):
        """ETF 모드(asset_mode='etf') 에서 일반 주식 심볼은 건너뜀."""
        svc.adapter.api_type = 'mock'
        svc.adapter.is_etf = lambda code: code == '069500'

        _analysis_stock = dict(self._MOCK_ANALYSIS_BUY)

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=_analysis_stock):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],   # 일반 주식
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                asset_mode='etf',    # ETF 전용 모드
                max_orders=5,
                allow_live_order=False,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={'profitability_validation': {'enabled': False}},
            )

        # 일반 주식 005930 은 ETF 모드에서 필터링되어 주문 건너뜀
        assert result['orders_executed'] == 0

    def test_run_auto_trade_cycle_profitability_blocked(self, svc):
        """수익성 KPI 미달 시 모든 심볼에 profitability_blocked SKIP 반환."""
        svc.adapter.api_type = 'mock'

        # 거래 20건 이상 + 저승률(0%) → KPI 차단
        bad_trades = [{'pnl': -100.0, 'fee': 0.0, 'quantity': 1.0, 'price': 10000.0} for _ in range(25)]
        svc._get_recent_trade_samples = lambda *a, **kw: bad_trades

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                max_orders=5,
                allow_live_order=False,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={
                    'profitability_validation': {
                        'enabled': True,
                        'min_trades': 5,
                        'min_win_rate': 0.99,   # 사실상 불통과 조건
                    },
                    'strategy_engine': {'enabled': False},
                },
            )

        assert result['status'] == 'ok'
        assert result['orders_executed'] == 0
        skip_decisions = [d for d in result['decisions'] if d.get('reason') == 'profitability_blocked']
        assert len(skip_decisions) >= 1

    def test_run_auto_trade_cycle_profitability_bypassed_on_few_trades(self, svc):
        """거래 데이터 부족 시 수익성 검증 bypass → 주문 차단 없음."""
        svc.adapter.api_type = 'mock'
        svc.adapter.place_order.return_value = {
            'status': 'success', 'order_id': 'PV-BYPASS-1',
            'execution_mode': 'mock', 'success': True,
        }

        # 3건만 → min_trades(20) 미달 → bypass → 차단 안 됨
        few_trades = [
            {'pnl': 100.0, 'fee': 0.0, 'quantity': 1.0, 'price': 10000.0} for _ in range(3)
        ]
        svc._get_recent_trade_samples = lambda *a, **kw: few_trades

        with patch.object(svc, 'get_market_regime', return_value='range'), \
             patch.object(svc, 'analyze_symbol', return_value=dict(self._MOCK_ANALYSIS_BUY)):
            result = svc.run_auto_trade_cycle(
                symbols=['005930'],
                quantity=1,
                order_type='MARKET',
                buy_threshold=35,
                sell_threshold=10,
                max_orders=5,
                allow_live_order=False,
                guardrails={'enabled': False},
                exit_policy={'enable_exit_policy': False},
                auto_risk_policy={
                    'profitability_validation': {'enabled': True},
                    'strategy_engine': {'enabled': False},
                },
            )

        assert result['status'] == 'ok'
        skip_decisions = [d for d in result['decisions'] if d.get('reason') == 'profitability_blocked']
        assert len(skip_decisions) == 0
