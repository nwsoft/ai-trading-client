from __future__ import annotations

import pytest

from trading.position_sizing_policy import (
    calculate_position_sizing,
    derive_market_risk_multiplier,
    effective_position_limit,
)
from trading.execution_mode import ExecutionMode
from trading.unified_trader import UnifiedTrader
from trading.trader import Trader
from trading.analyzer import Analyzer


def _plan(**overrides):
    values = {
        "policy": {
            "mode": "account_risk",
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10.0,
            "max_notional_percent": 50.0,
        },
        "asset_class": "crypto_futures",
        "quote_currency": "USDT",
        "account_equity": 1000.0,
        "account_equity_source": "live_account",
        "price": 100.0,
        "stop_fraction": 0.01,
        "requested_leverage": 5,
        "leverage_cap": 5,
        "fixed_notional": 20.0,
        "risk_multiplier": 1.0,
        "contract_size": 1.0,
    }
    values.update(overrides)
    return calculate_position_sizing(**values)


def test_account_risk_sizing_compounds_with_equity():
    small = _plan(account_equity=1000.0)
    large = _plan(account_equity=2000.0)
    assert small["target_notional"] == pytest.approx(500.0)
    assert large["target_notional"] == pytest.approx(1000.0)
    assert large["target_quantity"] == pytest.approx(small["target_quantity"] * 2)


def test_stop_distance_controls_notional_at_same_loss_budget():
    tight = _plan(stop_fraction=0.01)
    wide = _plan(stop_fraction=0.02)
    assert tight["target_risk_amount"] == pytest.approx(wide["target_risk_amount"])
    assert wide["target_notional"] == pytest.approx(tight["target_notional"] / 2)


def test_recovery_multiplier_reduces_risk_and_notional():
    normal = _plan()
    recovery = _plan(risk_multiplier=0.20)
    assert recovery["target_risk_amount"] == pytest.approx(normal["target_risk_amount"] * 0.20)
    assert recovery["target_notional"] == pytest.approx(normal["target_notional"] * 0.20)
    assert "performance_risk_multiplier" in recovery["limiting_reasons"]


def test_market_multiplier_is_reduction_only_and_uses_fraction_units():
    assert derive_market_risk_multiplier(
        market_regime="NORMAL", volatility_fraction=0.0
    ) == pytest.approx(1.0)
    assert derive_market_risk_multiplier(
        market_regime="VOLATILE", volatility_fraction=0.0
    ) == pytest.approx(0.70)
    assert derive_market_risk_multiplier(
        market_regime="NORMAL", volatility_fraction=0.03
    ) == pytest.approx(0.70)
    plan = _plan(market_risk_multiplier=0.70)
    assert plan["target_risk_amount"] == pytest.approx(3.5)
    assert "market_risk_multiplier" in plan["limiting_reasons"]


def test_spot_and_stock_are_always_one_x():
    for asset in ("crypto_spot", "stock", "etf"):
        plan = _plan(asset_class=asset, requested_leverage=20, leverage_cap=20)
        assert plan["effective_leverage"] == 1
        assert plan["estimated_margin"] == pytest.approx(plan["target_notional"])


def test_contract_size_translates_notional_without_changing_risk():
    base = _plan(contract_size=1.0)
    contracts = _plan(contract_size=0.01)
    assert contracts["target_notional"] == pytest.approx(base["target_notional"])
    assert contracts["target_quantity"] == pytest.approx(base["target_quantity"] * 100)


def test_existing_accounts_require_explicit_legacy_adapter_migration():
    plan = _plan(policy={}, account_equity=100000.0, requested_leverage=5)
    assert plan["mode"] == "legacy_venue"
    assert plan["allowed"] is False
    assert plan["reason"] == "legacy_venue_adapter_required"


def test_manual_notional_never_silently_expands():
    plan = _plan(
        policy={"mode": "manual_notional"},
        account_equity=100000.0,
        requested_leverage=5,
    )
    assert plan["mode"] == "manual_notional"
    assert plan["target_notional"] == pytest.approx(20.0)
    assert plan["authorized_notional_cap"] == pytest.approx(20.0)


def test_strategy_risk_request_is_effective_but_cannot_raise_account_master_cap():
    conservative = _plan(strategy_risk_model={"risk_per_trade_percent": 0.25})
    aggressive = _plan(strategy_risk_model={"risk_per_trade_percent": 2.0})
    assert conservative["risk_per_trade_percent"] == pytest.approx(0.25)
    assert conservative["target_risk_amount"] == pytest.approx(2.5)
    assert aggressive["risk_per_trade_percent"] == pytest.approx(0.5)
    assert aggressive["target_risk_amount"] == pytest.approx(5.0)
    assert "account_risk_cap" in aggressive["limiting_reasons"]


def test_strategy_position_request_and_performance_can_only_reduce_account_cap():
    raised = effective_position_limit(
        3,
        strategy_risk_model={"max_concurrent_positions": 10},
    )
    reduced = effective_position_limit(
        10,
        strategy_risk_model={"max_concurrent_positions": 5},
        performance_limit=3,
    )
    assert raised["effective_max_positions"] == 3
    assert reduced["effective_max_positions"] == 3


def test_ai_threshold_runtime_overlay_expires_without_rewriting_user_base(monkeypatch):
    analyzer = object.__new__(Analyzer)
    analyzer.settings = {"signal_thresholds": {"rsi_oversold": 30}}
    analyzer.user_signal_threshold = 70
    analyzer.exchange_signal_thresholds = {}
    analyzer.runtime_signal_threshold_overlays = {}
    analyzer.runtime_user_signal_thresholds = {}
    analyzer._exchange_context_local = type("Local", (), {"value": "binance"})()
    analyzer.set_runtime_signal_threshold(60, exchange_name="binance", expires_at=200.0)
    analyzer.set_runtime_indicator_thresholds(
        {"rsi_oversold": 25}, exchange_name="binance", expires_at=200.0
    )
    monkeypatch.setattr("trading.analyzer.time.time", lambda: 100.0)
    assert analyzer.get_user_signal_threshold("binance") == 60
    assert analyzer._get_signal_thresholds()["rsi_oversold"] == 25
    assert analyzer.settings["signal_thresholds"]["rsi_oversold"] == 30
    monkeypatch.setattr("trading.analyzer.time.time", lambda: 300.0)
    assert analyzer.get_user_signal_threshold("binance") == 70
    assert analyzer._get_signal_thresholds()["rsi_oversold"] == 30


def test_account_risk_fails_closed_without_equity_or_stop():
    assert _plan(account_equity=0)["reason"] == "account_equity_unavailable"
    assert _plan(stop_fraction=0)["reason"] == "stop_distance_unavailable"


@pytest.mark.parametrize(
    "venue,price,contract,expected_notional",
    [
        ("upbit", 10_000.0, 1.0, 100_000.0),
        ("bithumb", 10_000.0, 1.0, 100_000.0),
        ("bybit", 100.0, 1.0, 250.0),
        ("bitget", 100.0, 0.1, 250.0),
        ("okx", 100.0, 0.01, 250.0),
    ],
)
def test_unified_venues_translate_one_account_risk_contract(
    venue, price, contract, expected_notional
):
    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "min_trade_amount": 20.0,
        "position_sizing_policy": {
            "mode": "account_risk",
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10.0,
            "max_notional_percent": 50.0,
            "paper_equity_usdt": 1_000.0,
            "paper_equity_krw": 1_000_000.0,
        },
    }
    trader.logger = type("Logger", (), {"info": lambda *args, **kwargs: None, "warning": lambda *args, **kwargs: None})()
    trader._execution_mode = lambda _venue: ExecutionMode.PAPER
    trader._effective_leverage_policy = lambda *_args, **_kwargs: {"effective": 5}
    trader._ccxt_contract_size = lambda *_args, **_kwargs: contract
    params = {"sl_percent": 0.02, "leverage": 5}

    quantity = trader._calculate_position_size_unified(
        venue,
        "TEST",
        {"current_price": price},
        params,
        cold_start={"risk_multiplier": 1.0},
    )

    plan = params["_position_sizing"]
    assert plan["allowed"] is True
    assert plan["effective_leverage"] == (1 if venue in {"upbit", "bithumb"} else 3)
    assert quantity * price * contract == pytest.approx(expected_notional)


def test_unified_live_equity_prefers_total_over_free_balance():
    class Client:
        @staticmethod
        def get_balance():
            return {"USDT": {"total": 1_000.0, "free": 100.0}}

    trader = object.__new__(UnifiedTrader)
    trader.settings = {"position_sizing_policy": {"mode": "account_risk"}}
    trader._execution_mode = lambda _venue: ExecutionMode.LIVE
    trader.get_exchange_client = lambda _venue: Client()

    equity, source = trader._position_sizing_equity("okx", quote_currency="USDT")

    assert equity == 1_000.0
    assert source == "live_account_equity"


def test_unified_percent_point_volatility_is_normalized_before_risk_overlay():
    trader = object.__new__(UnifiedTrader)
    trader.settings = {
        "min_trade_amount": 20.0,
        "position_sizing_policy": {
            "mode": "account_risk",
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10.0,
            "max_notional_percent": 50.0,
            "paper_equity_usdt": 1_000.0,
        },
    }
    trader.logger = type(
        "Logger", (), {
            "info": lambda *args, **kwargs: None,
            "warning": lambda *args, **kwargs: None,
        }
    )()
    trader._execution_mode = lambda _venue: ExecutionMode.PAPER
    trader._effective_leverage_policy = lambda *_args, **_kwargs: {"effective": 5}
    trader._ccxt_contract_size = lambda *_args, **_kwargs: 1.0
    params = {"sl_percent": 0.01, "leverage": 5}

    trader._calculate_position_size_unified(
        "bybit",
        "BTC/USDT:USDT",
        {
            "current_price": 100.0,
            "market_regime": "NORMAL",
            "market_volatility": 3.0,
        },
        params,
        cold_start={"risk_multiplier": 1.0},
    )

    assert params["_position_sizing"]["market_risk_multiplier"] == pytest.approx(0.70)


def test_binance_account_risk_quantity_is_stamped_before_authorization():
    class Client:
        @staticmethod
        def get_balance_snapshot():
            return {
                "balance": {"USDT": {"available_balance": 200.0}},
                "account_info": {
                    "total_margin_balance": 1_000.0,
                    "available_balance": 200.0,
                },
            }

        @staticmethod
        def get_current_price(_symbol):
            return 100.0

    trader = object.__new__(Trader)
    trader.binance_client = Client()
    trader.settings = {
        "min_trade_amount": 20.0,
        "max_leverage": 5,
        "position_sizing_policy": {
            "mode": "account_risk",
            "risk_per_trade_percent": 0.5,
            "max_margin_usage_percent": 10.0,
            "max_notional_percent": 50.0,
            "paper_equity_usdt": 1_000.0,
        },
    }
    trade = {
        "symbol": "BTCUSDT", "price": 100.0, "qty": 0.2,
        "sl": 0.01, "leverage": 5, "risk_multiplier": 1.0,
    }

    plan = trader._prepare_binance_pre_authorization_sizing(trade, dry_run=False)

    assert plan["account_equity_source"] == "live_total_margin_balance"
    assert plan["target_notional"] == pytest.approx(500.0)
    assert trade["qty"] == pytest.approx(5.0)
    assert trade["_position_sizing"] == plan


def test_binance_learning_sizing_never_reads_live_balance():
    class Client:
        @staticmethod
        def get_balance_snapshot():
            raise AssertionError("LEARNING must not read private balance")

        @staticmethod
        def get_current_price(_symbol):
            return 100.0

    trader = object.__new__(Trader)
    trader.binance_client = Client()
    trader.settings = {
        "min_trade_amount": 20.0,
        "max_leverage": 5,
        "position_sizing_policy": {
            "mode": "account_risk", "paper_equity_usdt": 1_000.0,
        },
    }
    trade = {
        "symbol": "BTCUSDT", "price": 100.0, "qty": 0.2,
        "sl": 0.01, "leverage": 5,
    }

    plan = trader._prepare_binance_pre_authorization_sizing(trade, dry_run=True)

    assert plan["allowed"] is True
    assert plan["account_equity_source"] == "learning_virtual_equity"
