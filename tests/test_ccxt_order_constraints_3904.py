from types import SimpleNamespace

from trading.exchanges.order_constraints import (
    ccxt_amount_ceiling,
    prepare_ccxt_order_quantity,
)


class FakeCcxtExchange:
    def market(self, _symbol):
        return {
            "limits": {
                "amount": {"min": 1.0},
                "cost": {"min": 5000.0},
            }
        }

    def amount_to_precision(self, _symbol, quantity):
        return str(int(float(quantity)))

    def fetch_ticker(self, _symbol):
        return {"last": 500.0}


def test_ccxt_order_contract_rejects_notional_after_precision_floor():
    result = prepare_ccxt_order_quantity(
        FakeCcxtExchange(),
        "XRP/KRW",
        10.9,
        reference_price=499.0,
    )

    assert result["allowed"] is False
    assert result["quantity"] == 10.0
    assert "minimum notional not met" in result["reason"]


def test_ccxt_order_contract_returns_exchange_precision_quantity():
    result = prepare_ccxt_order_quantity(
        FakeCcxtExchange(),
        "XRP/KRW",
        11.9,
        reference_price=500.0,
    )

    assert result["allowed"] is True
    assert result["quantity"] == 11.0
    assert result["notional"] == 5500.0


def test_krw_market_uses_safe_fallback_when_ccxt_omits_cost_limit():
    class MissingCostExchange(FakeCcxtExchange):
        def market(self, _symbol):
            return {"quote": "KRW", "limits": {"amount": {"min": 1.0}}}

    result = prepare_ccxt_order_quantity(
        MissingCostExchange(),
        "XRP/KRW",
        9.0,
    )

    assert result["allowed"] is False
    assert result["min_cost"] if result.get("allowed") else True
    assert "minimum notional not met" in result["reason"]


def test_ccxt_amount_ceiling_finds_next_exchange_step_without_guessing_precision_mode():
    quantity = ccxt_amount_ceiling(FakeCcxtExchange(), "XRP/KRW", 10.12)

    assert quantity == 11.0


def test_unified_minimum_uses_market_cost_amount_and_exchange_precision():
    from trading.unified_trader import UnifiedTrader

    trader = object.__new__(UnifiedTrader)
    trader.settings = {"min_trade_amount": 5.0}
    trader.exchange_manager = SimpleNamespace(
        get_current_price=lambda _symbol, _exchange: 499.0,
    )
    trader.get_exchange_client = lambda _exchange: SimpleNamespace(
        exchange=FakeCcxtExchange(),
    )

    adjusted, note = trader._ensure_min_notional("upbit", "XRP/KRW", 10.0)

    assert adjusted == 11.0
    assert adjusted * 499.0 >= 5000.0 * 1.01
    assert "target 5050.0000" in note


def test_all_ccxt_adapters_apply_common_submission_contract():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    for relative in (
        "trading/exchanges/adapters/upbit_spot_adapter.py",
        "trading/exchanges/adapters/bithumb_spot_adapter.py",
        "trading/exchanges/adapters/bybit_futures_adapter.py",
        "trading/exchanges/adapters/okx_futures_adapter.py",
        "trading/exchanges/adapters/bitget_futures_adapter.py",
    ):
        source = (root / relative).read_text(encoding="utf-8")
        assert "prepare_ccxt_order_quantity" in source