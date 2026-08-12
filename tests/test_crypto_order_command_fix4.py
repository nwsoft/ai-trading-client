from trading.order_command_policy import (
    classify_order_error,
    client_order_params,
    exchange_client_order_id,
)
from trading.recorder import Recorder
from trading.unified_trader import UnifiedTrader


def test_crypto_order_command_claim_is_persistent_and_unique(tmp_path):
    db_path = str(tmp_path / "trading.db")
    first = Recorder(db_path=db_path, log_path=str(tmp_path / "logs"))
    claim = first.claim_crypto_order_command(
        command_id="entry:test:1",
        exchange="bybit",
        symbol="BTCUSDT",
        side="LONG",
        intent_type="entry",
        quantity=0.01,
    )
    assert claim["claimed"] is True
    assert first.update_crypto_order_command(
        "entry:test:1", status="submitting", increment_attempt=True
    ) is True

    restarted = Recorder(db_path=db_path, log_path=str(tmp_path / "logs"))
    duplicate = restarted.claim_crypto_order_command(
        command_id="entry:test:1",
        exchange="bybit",
        symbol="BTCUSDT",
        side="LONG",
        intent_type="entry",
        quantity=0.01,
    )
    assert duplicate["claimed"] is False
    assert duplicate["status"] == "submitting"
    assert duplicate["attempts"] == 1


def test_exchange_client_order_ids_are_bounded_and_mapped():
    value = exchange_client_order_id("order:" + "x" * 500)
    assert value.startswith("noah-")
    assert len(value) <= 32
    assert client_order_params("binance", "x") == {"newClientOrderId": exchange_client_order_id("x")}
    assert client_order_params("bybit", "x") == {"orderLinkId": exchange_client_order_id("x")}
    assert client_order_params("okx", "x") == {"clOrdId": exchange_client_order_id("x")}
    assert client_order_params("bitget", "x") == {"clientOid": exchange_client_order_id("x")}
    assert client_order_params("upbit", "x") == {"identifier": exchange_client_order_id("x")}
    assert client_order_params("bithumb", "x") == {}


def test_order_error_policy_never_blindly_retries_ambiguous_close():
    timeout = classify_order_error("HTTPS connection timeout after submit")
    assert timeout["category"] == "ambiguous_transport"
    assert timeout["reconcile"] is True
    assert timeout["halt_entries"] is True

    constraint = classify_order_error("Minimum notional not met")
    assert constraint["category"] == "order_constraint"
    assert constraint["retry"] is False

    rate_limit = classify_order_error("HTTP 429 too many requests")
    assert rate_limit == {
        "category": "rate_limit",
        "retry": True,
        "reconcile": False,
        "halt_entries": True,
        "delay": 30,
    }


def test_bybit_reconciliation_queries_order_link_id_before_retry():
    class Exchange:
        def privateGetV5OrderRealtime(self, request):
            assert request["orderLinkId"] == "noah-client-id"
            return {
                "result": {
                    "list": [{
                        "orderStatus": "Filled",
                        "orderId": "exchange-1",
                        "cumExecQty": "0.01",
                        "avgPrice": "50000",
                    }]
                }
            }

    class Adapter:
        exchange = Exchange()

        @staticmethod
        def _normalize_symbol(symbol):
            return "BTC/USDT:USDT"

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = type("Logger", (), {"warning": lambda *args: None})()
    result = trader._lookup_order_by_client_id(
        "bybit", Adapter(), "BTCUSDT", "noah-client-id"
    )
    assert result["status"] == "Filled"
    assert result["order_id"] == "exchange-1"
    assert result["filled"] == "0.01"
