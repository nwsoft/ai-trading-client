from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from trading.paper_strategy_ledger import (
    paper_outcome_calculation_status,
    paper_quote_currency,
    summarize_paper_outcomes,
)
from trading.smart_exit_policy import resolve_smart_exit_policy
from trading.trader import Position, PositionSide
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


def _closed(pnl_percent: float, symbol: str = "BTCUSDT") -> dict:
    return {"symbol": symbol, "pnl_percent": pnl_percent}


def test_smart_exit_is_deterministic_for_paper_and_live_inputs():
    kwargs = dict(
        baseline_tp=0.0018,
        baseline_sl=0.0020,
        closed_trades=[_closed(0.4), _closed(-0.2)] * 6,
        volatility=0.003,
        atr_fraction=0.0025,
        market_regime="NORMAL",
        fee_rate=0.0004,
        slippage_rate=0.0002,
        minimum_rr=1.2,
    )
    assert resolve_smart_exit_policy(**kwargs) == resolve_smart_exit_policy(**kwargs)


def test_exchange_pool_prevents_all_symbols_from_falling_back_to_one_fixed_value():
    result = resolve_smart_exit_policy(
        baseline_tp=0.0018,
        baseline_sl=0.0020,
        closed_trades=[_closed(0.3, "NEWUSDT")],
        fallback_closed_trades=[_closed(0.9), _closed(-0.25)] * 12,
        minimum_samples=10,
    )
    assert result["sample_scope"]["sufficient"] is False
    assert result["sample_scope"]["statistical_source"] == "exchange_pool"
    assert result["statistical"]["source"] == "exchange_pool_shrunk"
    assert result["final"]["tp"] != pytest.approx(0.0018)


def test_ai_custom_fixed_exit_is_immutable_and_unsafe_rr_is_rejected_not_rewritten():
    result = resolve_smart_exit_policy(
        baseline_tp=0.003,
        baseline_sl=0.0015,
        closed_trades=[_closed(3.0), _closed(-2.0)] * 20,
        volatility=0.04,
        strategy_owned=True,
        strategy_source="v1",
        minimum_rr=1.5,
    )
    assert result["final"] == {"tp": 0.003, "sl": 0.0015, "source": "ai_custom_declared"}
    assert result["entry_allowed"] is True

    rejected = resolve_smart_exit_policy(
        baseline_tp=0.001,
        baseline_sl=0.003,
        strategy_owned=True,
        minimum_rr=1.0,
    )
    assert rejected["final"]["tp"] == 0.001
    assert rejected["final"]["sl"] == 0.003
    assert rejected["entry_allowed"] is False


def test_general_policy_never_widens_configured_stop():
    result = resolve_smart_exit_policy(
        baseline_tp=0.0018,
        baseline_sl=0.0020,
        volatility=0.05,
        minimum_rr=1.5,
    )
    assert result["final"]["sl"] <= 0.0020
    assert result["final"]["tp"] / result["final"]["sl"] >= 1.5


def test_short_tp_sl_exit_reason_uses_short_price_direction():
    trader = object.__new__(Trader)
    trader.logger = logging.getLogger("short-exit-reason")
    position = Position(
        symbol="BTCUSDT", side=PositionSide.SHORT,
        entry_price=100.0, current_price=98.0, quantity=1.0,
        leverage=1, unrealized_pnl=2.0, unrealized_pnl_percent=2.0,
        entry_time=datetime.now(timezone.utc), tp_price=98.0, sl_price=101.0,
    )
    assert trader._determine_exit_reason(position) == "이익 목표 달성"
    position.current_price = 101.0
    assert trader._determine_exit_reason(position) == "손실 제한 도달"


@pytest.mark.parametrize(
    ("exchange", "symbol", "currency"),
    [
        ("upbit", "BTC/KRW", "KRW"),
        ("bithumb", "ETH/KRW", "KRW"),
        ("bybit", "BTC/USDT:USDT", "USDT"),
        ("bitget", "ETH/USDT:USDT", "USDT"),
        ("okx", "SOL/USDT:USDT", "USDT"),
    ],
)
def test_unified_paper_quote_currency_contract(exchange, symbol, currency):
    assert paper_quote_currency(exchange, symbol) == currency


def test_unified_pnl_fields_are_nonzero_and_match_ledger_contract():
    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "estimated_round_trip_fee_rate": 0.001,
        "estimated_slippage_rate": 0.0005,
    }
    trader.logger = logging.getLogger("paper-pnl-test")
    position = Position(
        symbol="BTC/USDT:USDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        current_price=110.0,
        quantity=2.0,
        leverage=1,
        unrealized_pnl=0.0,
        unrealized_pnl_percent=0.0,
        entry_time=datetime.now(timezone.utc),
    )
    result = trader._calculate_pnl_unified(position, 110.0)
    assert result["gross_pnl_ccy"] == pytest.approx(20.0)
    assert result["estimated_fees"] == pytest.approx(0.2)
    assert result["estimated_slippage"] == pytest.approx(0.1)
    assert result["net_pnl_ccy"] == pytest.approx(19.7)


def test_legacy_unified_zero_rows_are_unknown_not_losses_and_currency_is_separate():
    rows = [
        {"scope": "unified", "exchange": "bithumb", "net_pnl": 0, "fees": 0},
        {"scope": "unified", "exchange": "bithumb", "net_pnl": 1000, "fees": 50,
         "quote_currency": "KRW", "calculation_status": "valid"},
        {"scope": "unified", "exchange": "bybit", "net_pnl": 2, "fees": 0.1,
         "quote_currency": "USDT", "calculation_status": "valid"},
    ]
    assert paper_outcome_calculation_status(rows[0]) == "legacy_unverified"
    summary = summarize_paper_outcomes(rows, default_currency="USDT")
    assert summary["closed_count"] == 2
    assert summary["recorded_count"] == 3
    assert summary["unverified_count"] == 1
    assert summary["win_rate"] == 100.0
    assert summary["pnl_by_currency"] == {"KRW": 1000.0, "USDT": 2.0}
