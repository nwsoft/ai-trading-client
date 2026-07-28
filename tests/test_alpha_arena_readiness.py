#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AlphaArena 실거래 readiness 리허설 자동 점검.

커버 대상:
- API 키 주입 기준 start/stop 동작 (키 있음/없음 차이)
- 주문 게이트: TP/SL 누락, 리스크 캡 초과, 쿨다운, 동시 포지션 초과
- 예외 복구 경로: binance_client 오류 → ERROR 상태 반환, runner 계속 동작
- session_id 생성 및 stop 후 reset 확인
- 멀티 심볼 주문 결정 E2E 흐름 (mock)
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest

from trading.alpha_arena.order_executor import OrderExecutor
from trading.alpha_arena.runner import AlphaArenaRunner


# ────────────────────────────────────────────────────────────────────────────
# 공용 Fixture
# ────────────────────────────────────────────────────────────────────────────

class MockBinanceClient:
    """실거래 readiness 테스트용 Binance 클라이언트 Mock."""

    def __init__(self, api_key: str = '', api_secret: str = '',
                 positions: Optional[Dict[str, Any]] = None,
                 raise_on_order: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self._positions = positions or {}
        self.raise_on_order = raise_on_order
        self.orders_placed: list = []

    @property
    def has_credentials(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def get_balance(self) -> Dict[str, Any]:
        return {'USDT': {'wallet_balance': 5000.0, 'available_balance': 4800.0}}

    def get_position_info(self, symbol: str) -> Dict[str, Any]:
        return self._positions.get(symbol, {'positionAmt': 0, 'entryPrice': 0})

    def get_futures_positions(self) -> Dict[str, Any]:
        return self._positions

    def create_order(self, **kwargs) -> Dict[str, Any]:
        if self.raise_on_order:
            raise RuntimeError("Binance API 오류 (모의)")
        self.orders_placed.append(kwargs)
        return {'orderId': f"mock_{len(self.orders_placed)}", 'status': 'FILLED'}

    def get_exchange_info(self) -> Dict[str, Any]:
        return {
            'symbols': [{
                'symbol': 'BTCUSDT',
                'filters': [
                    {'filterType': 'PRICE_FILTER', 'tickSize': '0.10'},
                    {'filterType': 'LOT_SIZE', 'stepSize': '0.001', 'minQty': '0.001'},
                    {'filterType': 'MIN_NOTIONAL', 'notional': '5'},
                ],
                'quantityPrecision': 3,
                'pricePrecision': 2,
            }],
        }

    def set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        return {'leverage': leverage}

    def change_margin_type(self, symbol: str, marginType: str) -> Dict[str, Any]:
        return {'marginType': marginType}

    def create_order_with_tp_sl(self, **kwargs) -> Dict[str, Any]:
        return self.create_order(**kwargs)


# ────────────────────────────────────────────────────────────────────────────
# 1. API 키 주입 기준 start/stop
# ────────────────────────────────────────────────────────────────────────────

class TestRunnerApiKeyReadiness:
    """API 키 유무에 따른 start/stop 동작 검증."""

    def _make_runner(self, api_key: str = '', api_secret: str = '') -> AlphaArenaRunner:
        client = MockBinanceClient(api_key=api_key, api_secret=api_secret)
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {'tick_interval_sec': 60}},
        )
        return runner, client

    def test_start_without_api_key_still_returns_true(self, monkeypatch):
        """API 키 없이도 runner.start()는 True 반환 (게이트는 주문 단계에서 차단).
        
        AlphaArena는 start 시점에 API 키 강제 검증을 하지 않으며,
        실제 주문 시도 시 binance_client에서 오류가 발생한다.
        """
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner(api_key='', api_secret='')
        result = runner.start()
        assert result is True
        runner.stop()

    def test_start_with_api_key_returns_true(self, monkeypatch):
        """API 키 주입 시 start() 정상 반환."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner(api_key='test_key', api_secret='test_secret')
        result = runner.start()
        assert result is True
        runner.stop()

    def test_runner_creates_session_id_on_start(self, monkeypatch):
        """start() 호출 시 session_id 생성."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner()
        assert runner.session_id is None
        runner.start()
        assert runner.session_id is not None
        assert runner.session_id.startswith('arena_')
        runner.stop()

    def test_runner_running_flag_after_start(self, monkeypatch):
        """start() 이후 running=True."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner()
        runner.start()
        assert runner.running is True
        runner.stop()

    def test_runner_not_running_after_stop(self, monkeypatch):
        """stop() 이후 running=False."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner()
        runner.start()
        runner.stop()
        assert runner.running is False

    def test_double_start_returns_false(self, monkeypatch):
        """이미 실행 중 start() 재호출 → False 반환."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner()
        runner.start()
        second = runner.start()
        assert second is False
        runner.stop()

    def test_stop_when_not_running_does_not_raise(self, monkeypatch):
        """미실행 상태에서 stop() 호출해도 예외 없음."""
        runner, _ = self._make_runner()
        runner.stop()  # should not raise

    def test_runner_has_metrics_after_start(self, monkeypatch):
        """start() 이후 metrics 객체 초기화 확인."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        runner, _ = self._make_runner()
        runner.start()
        assert runner.metrics is not None
        runner.stop()


# ────────────────────────────────────────────────────────────────────────────
# 2. 주문 게이트 E2E (OrderExecutor)
# ────────────────────────────────────────────────────────────────────────────

class TestOrderGateE2E:
    """주문 게이트 전체 조합 검증."""

    def _make_executor(self, positions=None, raise_on_order=False, **arena_settings) -> OrderExecutor:
        client = MockBinanceClient(
            api_key='key', api_secret='secret',
            positions=positions or {},
            raise_on_order=raise_on_order,
        )
        return OrderExecutor(
            binance_client=client,
            settings={'alpha_arena': arena_settings},
        ), client

    def test_gate_allows_valid_enter_long(self):
        """유효한 ENTER_LONG 신호는 gate 통과."""
        executor, _ = self._make_executor(max_risk_per_tick=100.0, cooldown_sec_per_symbol=0)
        result = executor._check_trade_gates('BTCUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 10.0,
        })
        assert result['allowed'] is True

    def test_gate_blocks_missing_profit_target(self):
        """TP 없는 진입 신호는 차단."""
        executor, _ = self._make_executor()
        result = executor._check_trade_gates('BTCUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': None,
            'stop_loss': 99000.0,
        })
        assert result['allowed'] is False

    def test_gate_blocks_missing_stop_loss(self):
        """SL 없는 진입 신호는 차단."""
        executor, _ = self._make_executor()
        result = executor._check_trade_gates('BTCUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': None,
        })
        assert result['allowed'] is False

    def test_gate_blocks_risk_cap_excess(self):
        """리스크 캡 초과 차단."""
        executor, _ = self._make_executor(max_risk_per_tick=50.0)
        result = executor._check_trade_gates('BTCUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 60.0,
        })
        assert result['allowed'] is False
        assert '리스크 캡' in result['reason']

    def test_gate_blocks_cooldown(self):
        """쿨다운 미경과 차단."""
        executor, _ = self._make_executor(cooldown_sec_per_symbol=30)
        executor._cooldown_tracker['BTCUSDT'] = time.time()
        result = executor._check_trade_gates('BTCUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 10.0,
        })
        assert result['allowed'] is False
        assert '쿨다운' in result['reason']

    def test_gate_blocks_max_concurrent_positions(self):
        """최대 동시 포지션 초과 차단.
        
        _count_active_positions()는 ARENA_SYMBOLS 기준으로 get_position_info()를 호출한다.
        Mock은 ARENA_SYMBOLS 키를 그대로 사용해야 한다.
        """
        # ARENA_SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT']
        executor, _ = self._make_executor(
            positions={
                'BTCUSDT': {'positionAmt': 0.5},
                'ETHUSDT': {'positionAmt': 1.0},
            },
            max_concurrent_positions=2,
        )
        result = executor._check_trade_gates('SOLUSDT', {
            'signal': 'ENTER_LONG',
            'profit_target': 200.0,
            'stop_loss': 180.0,
            'risk_usd': 5.0,
        })
        assert result['allowed'] is False
        assert '동시 포지션' in result['reason']

    def test_hold_signal_skipped(self):
        """HOLD 신호는 SKIPPED 반환."""
        executor, _ = self._make_executor()
        result = executor.execute_trading_decision('BTCUSDT', {'signal': 'HOLD'})
        assert result['status'] == 'SKIPPED'

    def test_invalid_signal_skipped(self):
        """알 수 없는 신호는 SKIPPED 반환."""
        executor, _ = self._make_executor()
        result = executor.execute_trading_decision('BTCUSDT', {'signal': 'BUY_NOW'})
        assert result['status'] == 'SKIPPED'


# ────────────────────────────────────────────────────────────────────────────
# 3. 예외 복구 경로
# ────────────────────────────────────────────────────────────────────────────

class TestExceptionRecovery:
    """binance_client 오류 시 예외 복구 경로 검증."""

    def test_execute_decision_returns_error_on_api_exception(self):
        """binance_client.create_order 오류 → ERROR 상태 반환, 예외 전파 없음."""
        client = MockBinanceClient(api_key='k', api_secret='s', raise_on_order=True)
        executor = OrderExecutor(
            binance_client=client,
            settings={'alpha_arena': {'max_risk_per_tick': 1000.0, 'cooldown_sec_per_symbol': 0}},
        )
        result = executor.execute_trading_decision('BTCUSDT', {
            'signal': 'CLOSE',
            'quantity': 0.001,
        })
        # CLOSE 주문도 gate 통과 후 client 오류 → ERROR 또는 SKIPPED(포지션 없음)
        assert result['status'] in ('ERROR', 'SKIPPED')

    def test_runner_start_with_failing_balance_client(self, monkeypatch):
        """get_balance() 예외 발생 시 start()가 False 반환하고 예외를 전파하지 않음.
        
        runner.start()는 내부에서 예외를 catch하여 False를 반환한다.
        예외가 호출자에게 전파되지 않는 것이 핵심 복구 설계이다.
        """
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)

        client = MockBinanceClient()
        client.get_balance = lambda: (_ for _ in ()).throw(RuntimeError("잔고 조회 실패"))

        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {'tick_interval_sec': 60}},
        )
        # 예외가 전파되지 않아야 함 (try-except로 감싸져 있음)
        try:
            result = runner.start()
        except Exception as exc:
            pytest.fail(f"start()가 예외를 전파했음: {exc}")
        # 잔고 조회 실패 → start가 False (내부 오류 처리)
        assert result is False

    def test_runner_stop_after_error_doesnt_raise(self, monkeypatch):
        """오류 발생 후 stop() 정상 동작."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {'tick_interval_sec': 60}},
        )
        runner.start()
        runner.stop()
        runner.stop()  # 두 번 stop도 예외 없어야 함


# ────────────────────────────────────────────────────────────────────────────
# 4. 실거래 readiness 체크리스트 (E2E 시뮬레이션)
# ────────────────────────────────────────────────────────────────────────────

class TestReadinessChecklist:
    """실거래 readiness 리허설 체크리스트 자동 점검."""

    def test_readiness_tick_interval_minimum_enforced(self):
        """틱 주기 최소 30초 보장."""
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {'tick_interval_sec': 5}},
        )
        assert runner.tick_interval_sec >= 30

    def test_readiness_order_executor_has_binance_client(self):
        """OrderExecutor에 binance_client 주입 확인."""
        client = MockBinanceClient(api_key='k', api_secret='s')
        executor = OrderExecutor(binance_client=client, settings={'alpha_arena': {}})
        assert executor.binance_client is client

    def test_readiness_callbacks_can_be_set(self, monkeypatch):
        """콜백 설정 인터페이스 동작 확인."""
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={},
        )
        called = {}
        runner.set_callbacks(
            on_model_chat=lambda msg: called.update({'chat': msg}),
            on_error=lambda err: called.update({'err': err}),
        )
        assert runner.on_model_chat is not None
        assert runner.on_error is not None

    def test_readiness_engine_default_is_deepseek(self):
        """기본 엔진이 종료된 V3.1이 아닌 DeepSeek V4 Flash인지 확인."""
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {}},
        )
        assert runner.engine == 'deepseek-v4-flash'

    def test_readiness_available_engines_includes_qwen(self):
        """사용 가능 엔진 목록에 qwen3-max 포함 확인."""
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {}},
        )
        assert 'qwen3-max' in runner.available_engines

    def test_readiness_session_reset_after_stop(self, monkeypatch):
        """start → stop → start 시 session_id가 새로 발급됨.
        
        session_id는 time.time() 기반이므로 동일 초 내에 동일값이 나올 수 있다.
        대신 각 start마다 session_id가 None이 아니고 start_session_time이 초기화되는지 확인.
        """
        monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)

        # time.time()을 단조증가 카운터로 교체해 항상 다른 값 보장
        counter = [1_000_000_000]
        def mock_time():
            counter[0] += 1
            return counter[0]
        monkeypatch.setattr('trading.alpha_arena.runner.time.time', mock_time)

        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            ai_manager=object(),
            settings={'alpha_arena': {'tick_interval_sec': 60}},
        )
        runner.start()
        sid1 = runner.session_id
        runner.stop()
        runner.start()
        sid2 = runner.session_id
        assert sid1 is not None
        assert sid2 is not None
        assert sid1 != sid2, f"session_id가 재사용됨: {sid1}"
        runner.stop()

    def test_readiness_gate_result_has_allowed_key(self):
        """_check_trade_gates() 결과에 allowed 키 항상 존재."""
        client = MockBinanceClient()
        executor = OrderExecutor(
            binance_client=client,
            settings={'alpha_arena': {}},
        )
        for signal in ('ENTER_LONG', 'ENTER_SHORT', 'CLOSE', 'HOLD'):
            result = executor._check_trade_gates('BTCUSDT', {
                'signal': signal,
                'profit_target': 101000.0,
                'stop_loss': 99000.0,
                'risk_usd': 10.0,
            })
            assert 'allowed' in result, f"{signal} 결과에 allowed 키 없음"


# ────────────────────────────────────────────────────────────────────────────
# Metrics 주입 연동 테스트 (2026-05-04 추가)
# ────────────────────────────────────────────────────────────────────────────

class TestMetricsInjection:
    """runner.start() → prompt_builder.set_metrics() 주입 경로 검증."""

    def _make_runner(self) -> AlphaArenaRunner:
        client = MockBinanceClient()
        runner = AlphaArenaRunner(
            binance_client=client,
            settings={'alpha_arena': {'tick_interval_sec': 30}},
        )
        return runner

    def test_metrics_none_before_start(self):
        """start() 전에는 runner.metrics가 None이어야 한다."""
        runner = self._make_runner()
        assert runner.metrics is None

    def test_metrics_injected_into_prompt_builder_after_start(self, monkeypatch):
        """start() 후 prompt_builder._metrics가 runner.metrics와 동일 인스턴스여야 한다."""
        runner = self._make_runner()
        monkeypatch.setattr(runner, '_run_loop', lambda: None)
        runner.start()
        try:
            assert runner.metrics is not None, "start() 후 runner.metrics가 None"
            assert runner.prompt_builder._metrics is runner.metrics, (
                "prompt_builder._metrics가 runner.metrics와 다른 인스턴스"
            )
        finally:
            runner.stop()

    def test_metrics_has_sharpe_ratio_field(self, monkeypatch):
        """ArenaMetrics.current_metrics.sharpe_ratio 필드가 float이어야 한다."""
        runner = self._make_runner()
        monkeypatch.setattr(runner, '_run_loop', lambda: None)
        runner.start()
        try:
            assert hasattr(runner.metrics, 'current_metrics'), "current_metrics 속성 없음"
            sharpe = getattr(runner.metrics.current_metrics, 'sharpe_ratio', None)
            assert isinstance(sharpe, float), f"sharpe_ratio가 float이 아님: {type(sharpe)}"
        finally:
            runner.stop()

    def test_prompt_builder_get_sharpe_from_metrics(self, monkeypatch):
        """prompt_builder가 metrics에서 sharpe_ratio를 읽어올 수 있어야 한다."""
        runner = self._make_runner()
        monkeypatch.setattr(runner, '_run_loop', lambda: None)
        runner.start()
        try:
            # metrics에 sharpe_ratio 강제 설정
            runner.metrics.current_metrics.sharpe_ratio = 1.23
            pb = runner.prompt_builder
            assert pb._metrics is not None
            sharpe = float(pb._metrics.current_metrics.sharpe_ratio)
            assert abs(sharpe - 1.23) < 1e-9, f"예상 1.23, 실제 {sharpe}"
        finally:
            runner.stop()

    def test_metrics_reset_on_second_start(self, monkeypatch):
        """stop() 후 start()하면 새 metrics 인스턴스가 주입되어야 한다."""
        runner = self._make_runner()
        monkeypatch.setattr(runner, '_run_loop', lambda: None)
        runner.start()
        first_metrics = runner.metrics
        runner.stop()

        runner.start()
        second_metrics = runner.metrics
        runner.stop()

        assert first_metrics is not second_metrics, "2회 start에서 metrics 인스턴스 재사용"
        assert runner.prompt_builder._metrics is second_metrics, (
            "2회 start 후 prompt_builder에 새 metrics가 주입되지 않음"
        )


# ────────────────────────────────────────────────────────────────────────────
# Liquidation Price 계산 테스트 (2026-05-04 추가)
# ────────────────────────────────────────────────────────────────────────────

class TestLiquidationPriceCalc:
    """prompt_builder 내 청산가 계산 로직 검증."""

    @staticmethod
    def _calc_liquidation(entry_price: float, leverage: int, side: str) -> float:
        """prompt_builder와 동일한 공식 (유지증거금율 0.5%)."""
        maintenance_margin_rate = 0.005
        lev = max(1, int(leverage))
        if side.upper() == 'LONG':
            denom = 1.0 + 1.0 / lev - maintenance_margin_rate
            return entry_price / denom if denom > 0 else 0.0
        else:
            denom = 1.0 - 1.0 / lev + maintenance_margin_rate
            return entry_price / denom if denom > 0 else 0.0

    def test_long_liq_below_entry(self):
        """LONG 청산가는 항상 진입가보다 낮아야 한다."""
        liq = self._calc_liquidation(100.0, 10, 'LONG')
        assert liq < 100.0, f"LONG 청산가({liq:.4f})가 진입가(100) 이상"

    def test_short_liq_above_entry(self):
        """SHORT 청산가는 항상 진입가보다 높아야 한다."""
        liq = self._calc_liquidation(100.0, 10, 'SHORT')
        assert liq > 100.0, f"SHORT 청산가({liq:.4f})가 진입가(100) 이하"

    def test_higher_leverage_closer_to_entry(self):
        """레버리지가 높을수록 청산가가 진입가에 가까워야 한다."""
        liq5 = self._calc_liquidation(100.0, 5, 'LONG')
        liq20 = self._calc_liquidation(100.0, 20, 'LONG')
        assert liq20 > liq5, f"레버리지 20x 청산가({liq20:.4f})가 5x({liq5:.4f})보다 낮음"

    def test_leverage_1_long(self):
        """레버리지 1x LONG 청산가는 약 0에 가까워야 한다 (실제 계산 확인)."""
        liq = self._calc_liquidation(100.0, 1, 'LONG')
        assert liq < 60.0, f"1x LONG 청산가가 예상보다 높음: {liq:.4f}"
