from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
from trading.exchanges.adapters.bitget_futures_adapter import BitgetFuturesAdapter
from trading.exchanges.adapters.bybit_futures_adapter import BybitFuturesAdapter
from trading.exchanges.adapters.okx_futures_adapter import OkxFuturesAdapter
from trading.exchanges.adapters.upbit_spot_adapter import UpbitSpotAdapter
from trading.exchanges.venue_capabilities import (
    CRYPTO_VENUES,
    STOCK_VENUES,
    SUPPORTED_VENUES,
    public_venue_registry,
    signal_execution_action,
    validate_entry_direction,
    venue_capabilities,
    venue_service,
    validate_venue_onboarding_profile,
)
from trading.unified_trader import UnifiedTrader
from trading import execution_mode, position_limit_policy
from web_platform.application_services import ApplicationServices
from web_platform import headless_runtime, query_services, runtime_bridge
from web_platform.market_data import MultiSourcePublicMarketData


ROOT = Path(__file__).resolve().parents[1]


def _typescript_generated_registry(path: Path) -> dict:
    source = path.read_text(encoding="utf-8")
    matched = re.search(r"export const VENUE_REGISTRY = (.*) as const;", source, re.DOTALL)
    assert matched, f"VENUE_REGISTRY is missing from {path.relative_to(ROOT)}"
    return json.loads(matched.group(1))


def test_canonical_venue_registry_drives_runtime_statistics_and_ui_inventory():
    assert SUPPORTED_VENUES == CRYPTO_VENUES | STOCK_VENUES
    assert {venue for venue in SUPPORTED_VENUES if venue_service(venue) == "blockchain"} == CRYPTO_VENUES
    assert {venue for venue in SUPPORTED_VENUES if venue_service(venue) == "stock"} == STOCK_VENUES
    assert query_services.CRYPTO_SOURCES == set(CRYPTO_VENUES)
    assert query_services.STOCK_SOURCES == set(STOCK_VENUES)
    assert runtime_bridge.CRYPTO_SOURCES == set(CRYPTO_VENUES)
    assert runtime_bridge.STOCK_SOURCES == set(STOCK_VENUES)
    assert headless_runtime.CRYPTO_SOURCES == set(CRYPTO_VENUES)
    assert execution_mode.CRYPTO_EXCHANGES == set(CRYPTO_VENUES)
    assert set(position_limit_policy.CRYPTO_EXCHANGES) == set(CRYPTO_VENUES)
    assert MultiSourcePublicMarketData.SOURCES == set(CRYPTO_VENUES)

    inventory = json.loads((ROOT / "config/web_ui_feature_inventory.json").read_text(encoding="utf-8"))
    services = {item["id"]: set(item.get("sources") or []) for item in inventory["services"]}
    assert services["blockchain"] == set(CRYPTO_VENUES)
    assert services["stock"] == set(STOCK_VENUES)

    generated_registry = _typescript_generated_registry(ROOT / "webui/src/generatedVenueRegistry.ts")
    assert generated_registry == public_venue_registry()
    assert {
        item["client_id"] for item in generated_registry["venues"]
        if item["service"] == "blockchain"
    } == set(CRYPTO_VENUES)
    assert {
        item["client_id"] for item in generated_registry["venues"]
        if item["service"] == "stock"
    } == set(STOCK_VENUES)
    onboarding = {
        item["client_id"]: item["onboarding_status"]
        for item in generated_registry["venues"]
    }
    assert onboarding["coinone"] == "source_ready_account_e2e_required"
    assert all(
        status == "live_ready"
        for venue, status in onboarding.items()
        if venue != "coinone"
    )

    contracts_source = (ROOT / "web_platform/contracts.py").read_text(encoding="utf-8")
    account_contract = re.search(
        r"class AccountSnapshotRequestContract.*?sources:\s*list\[Literal\[(.*?)\]\]",
        contracts_source,
        re.DOTALL,
    )
    assert account_contract
    assert set(re.findall(r'[\"\']([a-zA-Z0-9_-]+)[\"\']', account_contract.group(1))) == set(SUPPORTED_VENUES)

    for venue in CRYPTO_VENUES:
        assert ApplicationServices._statistics_view_key("blockchain", venue) == f"blockchain:{venue}"
    for venue in STOCK_VENUES:
        assert ApplicationServices._statistics_view_key("stock", venue) == f"stock:{venue}"


def test_unknown_or_cross_service_venue_fails_closed():
    assert venue_service("future-unknown") == ""
    with pytest.raises(ValueError, match="unsupported_statistics_source"):
        ApplicationServices._statistics_view_key("blockchain", "kiwoom")
    with pytest.raises(ValueError, match="unsupported_statistics_source"):
        ApplicationServices._statistics_view_key("stock", "binance")


class FakeKrwCcxt:
    def __init__(self, *, last: float = 3_000_000.0):
        self.last = last
        self.orders = []

    def market(self, symbol):
        return {
            "symbol": symbol,
            "base": symbol.split("/", 1)[0],
            "quote": "KRW",
            "limits": {"amount": {"min": 0.000001}, "cost": {"min": 5000.0}},
        }

    def amount_to_precision(self, _symbol, amount):
        return f"{float(amount):.8f}"

    def cost_to_precision(self, _symbol, cost):
        return str(int(float(cost)))

    def fetch_ticker(self, _symbol):
        return {"last": self.last}

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"id": "order-1", **kwargs}


class FakeFuturesCcxt:
    def __init__(self):
        self.orders = []
        self.markets = {
            "BTC/USDT:USDT": {
                "symbol": "BTC/USDT:USDT",
                "base": "BTC",
                "quote": "USDT",
                "limits": {"amount": {"min": 0.001}, "cost": {"min": 5.0}},
            }
        }

    def market(self, symbol):
        return self.markets[symbol]

    def amount_to_precision(self, _symbol, amount):
        return f"{float(amount):.3f}"

    def fetch_ticker(self, _symbol):
        return {"last": 50_000.0}

    def fetch_positions(self):
        return []

    def create_order(self, **kwargs):
        self.orders.append(kwargs)
        return {"id": "futures-order-1", **kwargs}


def test_venue_matrix_separates_krw_spot_and_usdt_futures():
    for venue in ("upbit", "bithumb"):
        caps = venue_capabilities(venue)
        assert caps["market_type"] == "spot"
        assert caps["quote_currency"] == "KRW"
        assert caps["can_short"] is False
        assert caps["can_leverage"] is False

    for venue in ("binance", "bybit", "okx", "bitget"):
        caps = venue_capabilities(venue)
        assert caps["market_type"] == "futures"
        assert caps["quote_currency"] == "USDT"
        assert caps["can_short"] is True


def test_future_ccxt_venue_requires_native_conformance_contracts():
    profile = {
        "venue": "futurex", "adapter_family": "ccxt",
        "market_type": "futures", "quote_currency": "USDT",
        "order_amount_unit": "contracts", "requires_contract_size": True,
        "can_short": True, "can_leverage": True,
        "onboarding_status": "live_ready",
        "paper_supported": True,
        "live_supported": True,
        "position_mode_contract": "oneway_and_hedge",
        "protective_order_contract": "venue_algo_orders",
        "reconciliation_contract": "orders_trades_positions",
        "client_order_id_contract": "supported",
        "fee_contract": "fills",
        "time_sync_contract": "server_offset",
        "rate_limit_contract": "bounded_backoff",
        "runtime_event_contract": "noahai.execution.v1",
        "xai_contract": "noahai.xai.v1",
        "execution_mode_contract": "learning_paper_live",
        "native_escape_hatches": ["protective_orders", "position_mode"],
    }
    assert validate_venue_onboarding_profile(profile) == (True, [])
    broken = dict(profile)
    broken.pop("protective_order_contract")
    broken["native_escape_hatches"] = []
    ok, errors = validate_venue_onboarding_profile(broken)
    assert ok is False
    assert "missing:protective_order_contract" in errors
    assert "ccxt_native_escape_hatches_not_declared" in errors


def test_spot_short_signal_is_managed_exit_never_new_short():
    assert signal_execution_action("upbit", "SHORT") == "skip_unowned_exit"
    assert signal_execution_action(
        "upbit", "SHORT", has_managed_long=True
    ) == "exit_managed_long"
    assert signal_execution_action("bithumb", "LONG") == "open_long"
    assert validate_entry_direction("upbit", "SHORT")[0] is False

    for venue in ("binance", "bybit", "okx", "bitget"):
        assert signal_execution_action(venue, "SHORT") == "open_short"
        assert validate_entry_direction(venue, "SHORT") == (True, "open_short")


def test_upbit_market_buy_submits_krw_cost_not_base_quantity():
    exchange = FakeKrwCcxt(last=3_000_000.0)
    adapter = UpbitSpotAdapter("key", "secret")
    adapter.exchange = exchange
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None

    result = adapter.place_order(
        "XRP/KRW", "buy", 0.002, order_type="MARKET", client_order_id="noah-1"
    )

    assert result["id"] == "order-1"
    submitted = exchange.orders[0]
    assert submitted["amount"] == pytest.approx(0.002)
    assert submitted["price"] is None
    assert submitted["params"] == {"identifier": "noah-1", "cost": 6000.0}


def test_upbit_market_sell_submits_owned_base_quantity_without_cost():
    exchange = FakeKrwCcxt(last=3_000_000.0)
    adapter = UpbitSpotAdapter("key", "secret")
    adapter.exchange = exchange
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None

    adapter.place_order("XRP/KRW", "sell", 0.002, order_type="MARKET")

    submitted = exchange.orders[0]
    assert submitted["amount"] == pytest.approx(0.002)
    assert submitted["params"] == {}
    assert "cost" not in submitted["params"]


def test_bithumb_keeps_base_quantity_contract_and_does_not_copy_upbit_cost():
    exchange = FakeKrwCcxt(last=3_000_000.0)
    adapter = BithumbSpotAdapter("key", "secret")
    adapter.exchange = exchange
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None

    adapter.place_order("XRP/KRW", "buy", 0.002, order_type="MARKET")

    submitted = exchange.orders[0]
    assert submitted["amount"] == pytest.approx(0.002)
    assert submitted["price"] is None
    assert "params" not in submitted


def test_fast_regime_observation_is_cached_and_krw_symbol_is_normalized():
    calls = []

    def get_klines(symbol, interval, limit, exchange_name):
        calls.append((symbol, interval, limit, exchange_name))
        return [
            {"close": 100.0 + index, "volume": 10.0 + index}
            for index in range(20)
        ]

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {"market_regime_check_interval_seconds": 300}
    trader.exchange_manager = SimpleNamespace(get_klines=get_klines)
    trader.logger = SimpleNamespace(error=lambda *args, **kwargs: None)
    trader.log_event = lambda *args, **kwargs: None

    first = trader._evaluate_current_market_conditions_unified_fast("upbit", "BTCUSDT")
    second = trader._evaluate_current_market_conditions_unified_fast("upbit", "BTCUSDT")

    assert first == second
    assert calls == [("BTC/KRW", "15m", 20, "upbit")]


def test_adaptive_performance_query_is_not_reloaded_every_trade_cycle():
    calls = []

    class Recorder:
        def get_recent_trades(self, **kwargs):
            calls.append(kwargs)
            return [{"pnl_percent": 1.0}, {"pnl_percent": -0.5}]

    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {"market_regime_check_interval_seconds": 300}
    trader.risk_manager = SimpleNamespace(consecutive_losses=1)
    trader.recorder = Recorder()

    first = trader._adaptive_performance_context("okx")
    second = trader._adaptive_performance_context("okx")

    assert first == second == {"recent_win_rate": 0.5, "consecutive_losses": 1}
    assert calls == [{"coin": "", "exchange": "okx", "days": 14}]


def test_position_ledger_refuses_spot_short_even_if_future_refactor_bypasses_guard():
    errors = []
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {}
    trader.logger = SimpleNamespace(error=lambda message: errors.append(str(message)))

    trader._record_position_with_tp_sl(
        "upbit",
        "BTC/KRW",
        "SHORT",
        0.01,
        {"price": 100_000_000.0},
        {},
        execution_mode="paper",
    )

    assert errors
    assert "진입 방향 계약 위반" in errors[-1]


@pytest.mark.parametrize(
    ("adapter", "expected_client_key"),
    [
        (BybitFuturesAdapter("key", "secret"), "orderLinkId"),
        (BitgetFuturesAdapter("key", "secret", "pass"), "clientOid"),
    ],
)
def test_futures_adapters_keep_short_entry_and_reduce_only_close(
    adapter, expected_client_key
):
    exchange = FakeFuturesCcxt()
    adapter.exchange = exchange
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None

    short = adapter.place_order(
        "BTCUSDT", "sell", 0.002, order_type="MARKET", client_order_id="short-1"
    )
    close = adapter.place_order(
        "BTCUSDT",
        "buy",
        0.002,
        order_type="MARKET",
        client_order_id="close-1",
        reduce_only=True,
    )

    assert short["status"] == "success"
    assert close["status"] == "success"
    assert exchange.orders[0]["side"] == "sell"
    assert exchange.orders[0]["params"] == {expected_client_key: "short-1"}
    assert exchange.orders[1]["side"] == "buy"
    assert exchange.orders[1]["params"][expected_client_key] == "close-1"
    assert exchange.orders[1]["params"]["reduceOnly"] is True


def test_okx_futures_order_keeps_margin_mode_and_reduce_only_contract():
    exchange = FakeFuturesCcxt()
    adapter = OkxFuturesAdapter("key", "secret", "pass")
    adapter.exchange = exchange
    adapter.is_connected = True
    adapter.settings = {"default_margin_type": "CROSS"}
    adapter.log_event = lambda *args, **kwargs: None
    adapter._round_amount = lambda _symbol, quantity: quantity

    result = adapter.place_order(
        "BTCUSDT",
        "sell",
        0.002,
        order_type="MARKET",
        client_order_id="close-1",
        reduce_only=True,
    )

    assert result["status"] == "success"
    submitted = exchange.orders[0]
    assert submitted["side"] == "sell"
    assert submitted["params"]["clOrdId"] == "close-1"
    assert submitted["params"]["marginMode"] == "cross"
    assert submitted["params"]["reduceOnly"] is True
