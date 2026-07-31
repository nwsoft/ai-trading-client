from trading.exchanges.execution_history import (
    build_execution_capabilities,
    fetch_ccxt_execution_history,
)


class _TradesExchange:
    has = {"fetchMyTrades": True}

    def fetch_my_trades(self, symbol, limit=100):
        return [{
            "id": "t1",
            "order": "o1",
            "symbol": symbol,
            "side": "buy",
            "amount": 2,
            "price": 10,
        }]


class _OrdersFallbackExchange:
    has = {"fetchMyTrades": False, "fetchClosedOrders": True}

    def fetch_closed_orders(self, symbol, limit=100):
        return [
            {
                "id": "o2",
                "symbol": symbol,
                "side": "sell",
                "status": "closed",
                "filled": 3,
                "average": 12,
            },
            {"id": "open", "symbol": symbol, "status": "open", "filled": 0},
        ]


class _UnsupportedExchange:
    has = {
        "fetchMyTrades": False,
        "fetchClosedOrders": False,
        "fetchOrders": False,
    }


def test_fetches_and_normalizes_native_trade_history():
    rows, capability = fetch_ccxt_execution_history(
        _TradesExchange(),
        symbol="BTC/USDT:USDT",
        limit=10,
        symbol_formatter=lambda value: str(value).split(":")[0],
    )
    assert rows[0]["order"] == "o1"
    assert rows[0]["filled"] == 2
    assert rows[0]["cost"] == 20
    assert rows[0]["symbol"] == "BTC/USDT"
    assert capability["history_source"] == "fetch_my_trades"


def test_closed_order_fallback_excludes_unfilled_orders():
    rows, capability = fetch_ccxt_execution_history(
        _OrdersFallbackExchange(),
        symbol="BTC/USDT:USDT",
        limit=10,
    )
    assert [row["id"] for row in rows] == ["o2"]
    assert rows[0]["cost"] == 36
    assert capability["history_source"] == "fetch_closed_orders"


def test_unsupported_history_is_not_reported_as_no_trades_capability():
    rows, capability = fetch_ccxt_execution_history(
        _UnsupportedExchange(),
        symbol=None,
        limit=10,
    )
    assert rows == []
    assert capability["history_available"] is False
    assert capability["history_reason"] == "exchange_history_api_unsupported"
    assert build_execution_capabilities(_UnsupportedExchange())["live_order_receipt"] is True
