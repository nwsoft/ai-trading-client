import sqlite3
import threading
import time
from unittest.mock import patch
from datetime import datetime, timedelta

from trading.exchanges.adapters.bithumb_spot_adapter import BithumbSpotAdapter
from trading.exchanges.adapters.korea_investment_stock_adapter import KoreaInvestmentStockAdapter
from trading.exchanges.venue_capabilities import venue_capabilities
from trading.exchanges.exchange_factory import ExchangeFactory
from trading.exchanges.adapters.kiwoom_process_proxy import KiwoomProcessProxy
from web_platform.query_services import AccountQueryService


def test_spot_and_futures_capabilities_are_not_interchangeable():
    bithumb = venue_capabilities("bithumb")
    assert {key: bithumb[key] for key in (
        "venue", "market_type", "quote_currency", "can_short", "can_leverage"
    )} == {
        "venue": "bithumb", "market_type": "spot", "quote_currency": "KRW",
        "can_short": False, "can_leverage": False,
    }
    assert bithumb["adapter_family"] == "ccxt"
    assert bithumb["order_amount_unit"] == "base"
    assert venue_capabilities("upbit")["can_short"] is False
    assert venue_capabilities("binance")["can_short"] is True
    assert venue_capabilities("bybit")["market_type"] == "futures"


def test_bithumb_open_orders_are_queried_per_known_symbol():
    calls = []

    class Exchange:
        def fetch_open_orders(self, symbol):
            calls.append(symbol)
            return [{"id": f"open-{symbol}", "symbol": symbol}]

    adapter = BithumbSpotAdapter("key", "secret")
    adapter.exchange = Exchange()
    adapter.is_connected = True
    adapter._known_order_symbols.update({"BTC/KRW", "ETH/KRW"})
    adapter.log_event = lambda *args, **kwargs: None

    orders = adapter.get_open_orders()

    assert calls == ["BTC/KRW", "ETH/KRW"]
    assert {row["symbol"] for row in orders} == {"BTC/KRW", "ETH/KRW"}


def test_bithumb_open_orders_without_known_symbol_does_not_call_invalid_api():
    class Exchange:
        def fetch_open_orders(self, symbol):
            raise AssertionError("must not be called without a known symbol")

    adapter = BithumbSpotAdapter("key", "secret")
    adapter.exchange = Exchange()
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None
    assert adapter.get_open_orders() == []


def test_bithumb_durable_symbol_seed_is_not_silently_capped_at_twenty():
    calls = []

    class Exchange:
        def fetch_open_orders(self, symbol):
            calls.append(symbol)
            return []

    adapter = BithumbSpotAdapter("key", "secret", order_symbol_query_limit=100)
    adapter.exchange = Exchange()
    adapter.is_connected = True
    adapter.log_event = lambda *args, **kwargs: None
    adapter.seed_order_symbols([{"symbol": f"COIN{index}/KRW"} for index in range(25)])

    assert adapter.get_open_orders() == []
    assert len(calls) == 25
    assert adapter.get_open_order_coverage() == {
        "status": "covered_known_symbols", "known_symbols": 25,
        "queried_symbols": 25, "truncated": False,
    }


def test_bithumb_trade_history_retries_symbol_required_api_per_known_symbol():
    calls = []

    class Exchange:
        has = {"fetchMyTrades": True}

        def fetch_my_trades(self, symbol, limit=100, **kwargs):
            calls.append(symbol)
            if symbol is None:
                raise RuntimeError("fetchMyTrades() requires a symbol argument")
            return [{
                "id": f"trade-{symbol}", "order": f"order-{symbol}",
                "symbol": symbol, "side": "buy", "amount": 1, "price": 10,
            }]

    adapter = BithumbSpotAdapter("key", "secret")
    adapter.exchange = Exchange()
    adapter.is_connected = True
    adapter._known_order_symbols.update({"BTC/KRW", "ETH/KRW"})
    adapter.log_event = lambda *args, **kwargs: None

    trades = adapter.get_trade_history(limit=100)

    assert calls == [None, "BTC/KRW", "ETH/KRW"]
    assert {row["symbol"] for row in trades} == {"BTC/KRW", "ETH/KRW"}
    assert {row["order"] for row in trades} == {
        "order-BTC/KRW", "order-ETH/KRW",
    }


def test_kis_etf_quote_uses_current_official_contract():
    adapter = KoreaInvestmentStockAdapter(
        "user", "secret", account_no="1234567801", app_key="app", app_secret="secret"
    )
    adapter.is_connected = True
    calls = []

    def fake_get(path, params=None):
        calls.append((path, params))
        return {
            "rt_cd": "0",
            "output": {
                "stck_prpr": "35000", "prdy_ctrt": "1.2", "acml_vol": "100",
                "acml_tr_pbmn": "3500000", "nav": "34950", "trc_errt": "0.12",
                "dprt": "0.14", "etf_rprs_bstp_kor_isnm": "KOSPI200",
            },
        }

    adapter._get = fake_get
    metrics = adapter.get_etf_realtime_metrics("069500")

    assert calls == [("/uapi/etfetn/v1/quotations/inquire-price", {
        "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "069500",
    })]
    assert adapter._tr_id(calls[0][0], method="GET") == "FHPST02400000"
    assert metrics["nav"] == 34950
    assert metrics["status"] == "ok"


def test_kis_etf_list_uses_explicit_configured_universe_without_invalid_list_api():
    adapter = KoreaInvestmentStockAdapter(
        "user", "secret", account_no="1234567801",
        configured_etf_symbols=["069500", "KRW-069500", "229200"],
    )

    assert adapter.get_etf_list() == [
        {"code": "069500", "symbol": "069500", "name": "069500", "is_etf": True,
         "source": "configured_watchlist"},
        {"code": "229200", "symbol": "229200", "name": "229200", "is_etf": True,
         "source": "configured_watchlist"},
    ]


def test_web_windows_kiwoom_uses_process_main_thread_proxy(monkeypatch):
    monkeypatch.setenv("NOAHAI_ENABLE_WEB_RUNTIME", "1")
    settings = {
        "stock_broker_configs": {
            "kiwoom": {
                "api_type": "openapi_plus", "api_version": "pykiwoom",
                "id": "user", "password": "pw", "cert_password": "cert",
                "account_no": "12345678",
            }
        }
    }
    with patch("trading.exchanges.exchange_factory.platform.system", return_value="Windows"):
        adapter = ExchangeFactory.create_stock_exchange("kiwoom", settings)
    assert isinstance(adapter, KiwoomProcessProxy)


def test_kiwoom_proxy_terminates_only_its_owned_child_after_graceful_timeout():
    events = []

    class Connection:
        def send(self, payload): events.append(("send", payload))
        def close(self): events.append(("close",))

    class Process:
        alive = True
        def join(self, timeout=None): events.append(("join", timeout))
        def is_alive(self): return self.alive
        def terminate(self):
            events.append(("terminate",))
            self.alive = False

    adapter = KiwoomProcessProxy("user", "pw", "cert")
    adapter._connection = Connection()
    adapter._process = Process()
    adapter.is_connected = True

    assert adapter.disconnect() is True
    assert events == [("send", None), ("join", 3), ("terminate",), ("join", 3), ("close",)]
    assert adapter._process is None
    assert adapter._connection is None


def test_kiwoom_proxy_shutdown_does_not_wait_behind_long_running_rpc():
    events = []
    lock_acquired = threading.Event()
    release_lock = threading.Event()

    class Connection:
        def close(self): events.append(("close",))

    class Process:
        alive = True
        def join(self, timeout=None): events.append(("join", timeout))
        def is_alive(self): return self.alive
        def terminate(self):
            events.append(("terminate",))
            self.alive = False

    adapter = KiwoomProcessProxy("user", "pw", "cert")
    adapter._connection = Connection()
    adapter._process = Process()

    def hold_rpc_lock():
        with adapter._rpc_lock:
            lock_acquired.set()
            release_lock.wait(5)

    holder = threading.Thread(target=hold_rpc_lock)
    holder.start()
    assert lock_acquired.wait(1)
    started = time.monotonic()
    try:
        assert adapter.disconnect() is True
    finally:
        release_lock.set()
        holder.join(timeout=1)

    assert time.monotonic() - started < 2.0
    assert events == [("terminate",), ("join", 3), ("close",)]


def test_report_periods_keep_krw_and_usdt_separate_and_use_full_sql_count(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, asset_type TEXT,
            pnl REAL, net_pnl REAL, fee REAL, exit_time DATETIME, reason TEXT,
            order_id TEXT, exit_order_id TEXT, position_owner TEXT,
            reconciliation_status TEXT
        );
        CREATE TABLE exchange_execution_log (
            id INTEGER PRIMARY KEY, exchange TEXT, order_id TEXT, symbol TEXT,
            cost REAL, confirmation_status TEXT, executed_at DATETIME, created_at DATETIME
        );
        CREATE TABLE exchange_execution_capability (
            exchange TEXT PRIMARY KEY, history_available INTEGER,
            history_reason TEXT, historical_trades INTEGER,
            closed_orders_fallback INTEGER, checked_at DATETIME,
            history_complete INTEGER DEFAULT 0,
            coverage_start DATETIME, coverage_end DATETIME,
            coverage_reason TEXT DEFAULT 'bounded_or_incremental_history'
        );
        """
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = [
        (index, "BTCUSDT", "binance", "crypto", 1.0, 1.0, .1, now, "exit", f"b-{index}", f"bx-{index}", "noahai", "exchange_confirmed")
        for index in range(1, 121)
    ]
    rows.append((121, "BTC/KRW", "bithumb", "crypto", 1000.0, 1000.0, 10.0, now, "exit", "k-1", "kx-1", "noahai", "exchange_confirmed"))
    connection.executemany("INSERT INTO trade_log VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.executemany(
        "INSERT INTO exchange_execution_log VALUES (?, ?, ?, ?, ?, 'confirmed', ?, ?)",
        [
            (1, "binance", "bx-1", "BTCUSDT", 100.0, now, now),
            (2, "bithumb", "kx-1", "BTC/KRW", 50000.0, now, now),
        ],
    )
    connection.executemany(
        """INSERT INTO exchange_execution_capability (
               exchange, history_available, history_reason,
               historical_trades, closed_orders_fallback, checked_at
           ) VALUES (?, ?, ?, ?, ?, ?)""",
        [
            ("binance", 1, "available", 1, 0, now),
            ("bithumb", 0, "exchange_history_api_unsupported", 0, 0, now),
        ],
    )
    connection.commit()
    connection.close()

    report = AccountQueryService(str(db_path)).report_period_metrics(asset_class="crypto")
    today = report["periods"]["today"]

    assert today["closed_count"] == 121
    assert today["execution_count"] == 2
    assert today["pnl_by_currency"] == {"USDT": 120.0, "KRW": 1000.0}
    assert today["execution_notional_by_currency"] == {"USDT": 100.0, "KRW": 50000.0}
    assert today["linked_closed_count"] == 2
    assert today["execution_history_status"] == "partial"

    bithumb = AccountQueryService(str(db_path)).report_period_metrics(
        asset_class="crypto", source="bithumb"
    )["periods"]["today"]
    assert bithumb["execution_count"] == 1
    assert bithumb["execution_history_available"] is False
    assert bithumb["execution_history_status"] == "stored_only"

    binance = AccountQueryService(str(db_path)).report_period_metrics(
        asset_class="crypto", source="binance"
    )["periods"]["today"]
    assert binance["execution_count"] == 1
    assert binance["execution_history_status"] == "partial"
    assert binance["execution_history_reason"] == "bounded_or_incremental_history"


def test_trading_statistics_never_falls_back_from_execution_to_closed_count(tmp_path):
    db_path = tmp_path / "trading.db"
    connection = sqlite3.connect(db_path)
    connection.executescript(
        """
        CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, asset_type TEXT,
            pnl REAL, pnl_percent REAL, fee REAL, entry_price REAL, quantity REAL,
            entry_time DATETIME, exit_time DATETIME, reason TEXT
        );
        CREATE TABLE exchange_execution_log (
            id INTEGER PRIMARY KEY, exchange TEXT, order_id TEXT, symbol TEXT,
            cost REAL, confirmation_status TEXT, executed_at DATETIME, created_at DATETIME
        );
        """
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection.execute(
        "INSERT INTO trade_log VALUES (1, 'BTCUSDT', 'binance', 'crypto', 2, 1, .1, 100, 1, ?, ?, 'exit')",
        ((datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"), now),
    )
    connection.commit()
    connection.close()

    stats = AccountQueryService(str(db_path)).trading_statistics(asset_class="crypto")
    assert stats["closed_count"] == 1
    assert stats["execution_count"] == 0
    assert stats["display_trade_count"] == 0
