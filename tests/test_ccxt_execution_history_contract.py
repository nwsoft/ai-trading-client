from trading.exchanges.execution_history import (
    build_execution_capabilities,
    confirm_ccxt_order_execution,
    execution_is_confirmed,
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


def test_incremental_history_passes_since_cursor_to_ccxt():
    class _IncrementalExchange:
        has = {"fetchMyTrades": True}

        def __init__(self):
            self.calls = []

        def fetch_my_trades(self, symbol, since=None, limit=100):
            self.calls.append((symbol, since, limit))
            return []

    exchange = _IncrementalExchange()
    rows, capability = fetch_ccxt_execution_history(
        exchange,
        symbol="ETH/USDT:USDT",
        since_ms=1785730000000,
        limit=25,
    )

    assert rows == []
    assert exchange.calls == [("ETH/USDT:USDT", 1785730000000, 25)]
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


class _OrderOnlyExchange:
    has = {
        "fetchMyTrades": False,
        "fetchClosedOrders": False,
        "fetchOrders": False,
        "fetchOrder": True,
    }

    def fetch_order(self, order_id, symbol=None):
        return {
            "id": order_id,
            "symbol": symbol,
            "side": "buy",
            "status": "closed",
            "filled": 3,
            "average": 400,
            "cost": 1200,
            "timestamp": 1785502800000,
            "fee": {"cost": 0.3, "currency": "KRW"},
        }


def test_order_id_confirmation_recovers_fill_when_history_list_is_unsupported():
    confirmed = confirm_ccxt_order_execution(
        _OrderOnlyExchange(),
        {"id": "bithumb-order-1", "status": "open", "amount": 3},
        symbol="RLC/KRW",
    )

    assert confirmed["_execution_confirmed"] is True
    assert confirmed["_execution_confirmation_source"] == "fetch_order"
    assert confirmed["filled"] == 3
    assert confirmed["cost"] == 1200
    assert execution_is_confirmed(confirmed) is True


def test_pending_order_receipt_is_not_reported_as_execution():
    class _StillOpen:
        def fetch_order(self, order_id, symbol=None):
            return {
                "id": order_id,
                "symbol": symbol,
                "status": "open",
                "amount": 2,
                "filled": 0,
            }

    pending = confirm_ccxt_order_execution(
        _StillOpen(),
        {"id": "pending-1", "status": "new", "amount": 2},
        symbol="BTC/KRW",
    )
    assert pending["_execution_confirmed"] is False
    assert execution_is_confirmed(pending) is False
