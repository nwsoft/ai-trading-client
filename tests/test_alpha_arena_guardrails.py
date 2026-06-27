#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Alpha Arena 가드레일 및 런너 기본 동작 테스트"""

import time

from trading.alpha_arena.order_executor import OrderExecutor
from trading.alpha_arena.runner import AlphaArenaRunner


class DummyBinanceClient:
    def __init__(self, positions=None):
        self.positions = positions or {}

    def get_position_info(self, symbol: str):
        return self.positions.get(symbol, {'positionAmt': 0})

    def get_balance(self):
        return {
            'USDT': {
                'wallet_balance': 1000.0,
            }
        }


def test_runner_tick_interval_clamped_to_30_seconds():
    runner = AlphaArenaRunner(
        binance_client=DummyBinanceClient(),
        ai_manager=object(),
        settings={'alpha_arena': {'tick_interval_sec': 10}},
    )

    assert runner.tick_interval_sec == 30


def test_runner_start_and_stop(monkeypatch):
    monkeypatch.setattr(AlphaArenaRunner, '_run_loop', lambda self: None)

    runner = AlphaArenaRunner(
        binance_client=DummyBinanceClient(),
        ai_manager=object(),
        settings={'alpha_arena': {'tick_interval_sec': 60}},
    )

    assert runner.start() is True
    assert runner.running is True

    runner.stop()
    assert runner.running is False


def test_trade_gate_rejects_missing_tp_sl():
    executor = OrderExecutor(
        binance_client=DummyBinanceClient(),
        settings={'alpha_arena': {}},
    )

    result = executor._check_trade_gates('BTCUSDT', {'signal': 'ENTER_LONG', 'profit_target': None, 'stop_loss': None})

    assert result['allowed'] is False
    assert 'profit_target' in result['reason']


def test_trade_gate_rejects_risk_cap_excess():
    executor = OrderExecutor(
        binance_client=DummyBinanceClient(),
        settings={'alpha_arena': {'max_risk_per_tick': 100.0}},
    )

    result = executor._check_trade_gates(
        'BTCUSDT',
        {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 120.0,
        },
    )

    assert result['allowed'] is False
    assert '리스크 캡 초과' in result['reason']


def test_trade_gate_rejects_cooldown():
    executor = OrderExecutor(
        binance_client=DummyBinanceClient(),
        settings={'alpha_arena': {'cooldown_sec_per_symbol': 30}},
    )
    executor._cooldown_tracker['BTCUSDT'] = time.time()

    result = executor._check_trade_gates(
        'BTCUSDT',
        {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 10.0,
        },
    )

    assert result['allowed'] is False
    assert '쿨다운 미경과' in result['reason']


def test_trade_gate_rejects_max_concurrent_positions():
    client = DummyBinanceClient(
        positions={
            'BTCUSDT': {'positionAmt': 1},
            'ETHUSDT': {'positionAmt': 1},
        }
    )
    executor = OrderExecutor(
        binance_client=client,
        settings={'alpha_arena': {'max_concurrent_positions': 2}},
    )

    result = executor._check_trade_gates(
        'SOLUSDT',
        {
            'signal': 'ENTER_LONG',
            'profit_target': 101000.0,
            'stop_loss': 99000.0,
            'risk_usd': 10.0,
        },
    )

    assert result['allowed'] is False
    assert '최대 동시 포지션 초과' in result['reason']
