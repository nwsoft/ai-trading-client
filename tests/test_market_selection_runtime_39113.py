import logging
import threading
import time
from types import SimpleNamespace

from trading.evaluator import Evaluator
from trading.market_selection_runtime import RegimeStabilizer, SelectionSingleFlight
from trading.stock_analysis_service import detect_market_regime
from trading.stock_runtime_controller import StockRuntimeController


class _Analyzer:
    settings = {}
    binance_client = None


def test_selection_singleflight_runs_one_producer_and_copies_result():
    flight = SelectionSingleFlight()
    entered = threading.Event()
    release = threading.Event()
    calls = []
    results = []

    def producer():
        calls.append(1)
        entered.set()
        release.wait(1)
        return [{"symbol": "BTCUSDT"}]

    first = threading.Thread(target=lambda: results.append(flight.run("binance", producer)))
    second = threading.Thread(target=lambda: results.append(flight.run("binance", producer)))
    first.start()
    assert entered.wait(1)
    second.start()
    release.set()
    first.join(1)
    second.join(1)

    assert len(calls) == 1
    assert results == [[{"symbol": "BTCUSDT"}], [{"symbol": "BTCUSDT"}]]
    results[0][0]["symbol"] = "MUTATED"
    assert flight.run("binance", producer)[0]["symbol"] == "BTCUSDT"


def test_regime_stabilizer_accepts_initial_state_and_confirms_transition():
    stabilizer = RegimeStabilizer()
    assert stabilizer.observe("binance", "normal", now=0) == ("normal", False)
    assert stabilizer.observe(
        "binance", "bull", confirmations=2, min_dwell_seconds=600, now=601
    ) == ("normal", False)
    assert stabilizer.observe(
        "binance", "bull", confirmations=2, min_dwell_seconds=600, now=602
    ) == ("bull", True)


def test_exchange_ticker_snapshot_prefers_one_bulk_request():
    evaluator = Evaluator(_Analyzer(), None, settings={})
    calls = {"bulk": 0, "single": 0}

    class RawExchange:
        id = "upbit"

        def fetch_tickers(self, symbols):
            calls["bulk"] += 1
            return {symbol: {"symbol": symbol, "quoteVolume": 1000} for symbol in symbols}

        def fetch_ticker(self, symbol):
            calls["single"] += 1
            raise AssertionError("bulk-capable venue must not call per-symbol ticker")

    client = SimpleNamespace(exchange=RawExchange())
    evaluator._set_selection_context("upbit", client)
    rows = evaluator._fetch_exchange_tickers(client, [f"C{i}/KRW" for i in range(200)])

    assert calls == {"bulk": 1, "single": 0}
    assert len({row["symbol"] for row in rows.values()}) == 200


def test_non_binance_kline_batch_is_bounded_parallel_and_reused():
    state = {"active": 0, "max_active": 0, "calls": 0}
    lock = threading.Lock()

    class Manager:
        def get_klines(self, symbol, interval, limit, exchange):
            assert exchange == "upbit"
            with lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
                state["calls"] += 1
            time.sleep(0.02)
            with lock:
                state["active"] -= 1
            return [[0, 1, 2, 0.5, 1.5, 10]] * limit

    analyzer = _Analyzer()
    analyzer.exchange_manager = Manager()
    evaluator = Evaluator(
        analyzer,
        None,
        settings={"coin_selection_max_workers": 4, "market_kline_cache_ttl_seconds": 60},
    )
    evaluator._set_selection_context("upbit", SimpleNamespace())
    symbols = [f"C{i}/KRW" for i in range(12)]

    first = evaluator._get_multiple_context_klines(symbols, "15m", 20)
    second = evaluator._get_multiple_context_klines(symbols, "15m", 20)

    assert len(first) == len(second) == 12
    assert state["calls"] == 12
    assert 2 <= state["max_active"] <= 4


def test_coin_selection_deep_scores_only_configured_liquidity_buffer(monkeypatch):
    evaluator = Evaluator(
        _Analyzer(),
        None,
        settings={"coin_selection_detail_candidate_limit": 30, "coin_selection_cache_ttl_seconds": 0},
    )
    candidates = [
        {"symbol": f"C{i}USDT", "overall_score": 80 - i / 100, "snapshot_at": time.time()}
        for i in range(100)
    ]
    observed = []
    monkeypatch.setattr(evaluator, "_analyze_candidate_coins_by_exchange", lambda **kwargs: candidates)

    def select_final(coins, *args):
        observed.append(len(coins))
        return list(coins[:20])

    monkeypatch.setattr(evaluator, "_select_final_coins", select_final)
    monkeypatch.setattr(evaluator, "_evaluate_coins_with_ai", lambda *args, **kwargs: [])

    selected = evaluator.select_trading_coins(15, 5, exchange="binance")

    assert observed == [30]
    assert len(selected) == 20


def test_stale_selection_preserves_previous_verified_universe(monkeypatch):
    evaluator = Evaluator(
        _Analyzer(),
        None,
        settings={
            "coin_selection_cache_ttl_seconds": 0,
            "coin_selection_max_snapshot_age_seconds": 20,
        },
    )
    batches = [
        [{"symbol": "BTCUSDT", "overall_score": 91, "snapshot_at": time.time()}],
        [{"symbol": "OLDUSDT", "overall_score": 99, "snapshot_at": time.time() - 60}],
    ]
    monkeypatch.setattr(
        evaluator,
        "_analyze_candidate_coins_by_exchange",
        lambda **kwargs: batches.pop(0),
    )
    monkeypatch.setattr(evaluator, "_select_final_coins", lambda coins, *args: list(coins))
    monkeypatch.setattr(evaluator, "_evaluate_coins_with_ai", lambda *args, **kwargs: [])

    first = evaluator.select_trading_coins(0, 1, exchange="binance")
    evaluator._selection_singleflight.invalidate("binance")
    second = evaluator.select_trading_coins(0, 1, exchange="binance")

    assert first[0]["symbol"] == "BTCUSDT"
    assert second[0]["symbol"] == "BTCUSDT"
    assert second[0]["execution_eligible"] is True


def test_stock_regime_uses_five_session_index_history_before_intraday_fallback():
    class Adapter:
        def get_index_history(self, symbol, count=6):
            assert (symbol, count) == ("KOSPI", 6)
            return [{"close": value} for value in [100, 100.2, 100.5, 101, 101.2, 102]]

        def get_index_price(self, symbol):
            raise AssertionError("history-supported broker must not use intraday fallback")

    assert detect_market_regime(Adapter()) == "bull"


def test_stock_regime_sorts_reverse_chronological_broker_history():
    class Adapter:
        def get_index_history(self, symbol, count=6):
            return [
                {"date": date, "close": close}
                for date, close in [
                    ("20260827", 102),
                    ("20260826", 101.2),
                    ("20260825", 101),
                    ("20260824", 100.5),
                    ("20260821", 100.2),
                    ("20260820", 100),
                ]
            ]

    assert detect_market_regime(Adapter()) == "bull"


def test_stock_runtime_reuses_universe_and_analysis_service_between_cycles():
    settings = {
        "paper_trading": True,
        "enabled_stock_brokers": ["kis"],
        "stock_broker_configs": {
            "koreaInvestment": {"api_type": "mock", "api_version": "mock"}
        },
        "stock_auto_trading": {
            "symbols": ["005930"],
            "interval_sec": 60,
            "universe_cache_ttl_sec": 300,
        },
    }
    constructions = []

    class Adapter:
        api_type = "mock"
        api_version = "mock"
        broker_name = "koreaInvestment"
        is_connected = True

        def get_stock_list(self, market):
            return []

        def get_etf_list(self):
            return []

    class Service:
        def __init__(self, adapter, **kwargs):
            self.adapter = adapter
            constructions.append(self)

        def run_auto_trade_cycle(self, **kwargs):
            return {"orders_executed": 0, "execution_mode": kwargs["execution_mode_override"]}

    controller = StockRuntimeController(
        settings_provider=lambda: settings,
        adapter_factory=lambda broker, cfg: Adapter(),
        service_factory=Service,
        logger=logging.getLogger("stock-runtime-test"),
    )

    first, _ = controller._run_once("koreaInvestment")
    second, _ = controller._run_once("koreaInvestment")

    assert first["execution_mode"] == second["execution_mode"] == "paper"
    assert len(constructions) == 1
    assert controller._universe_cache["koreaInvestment"][2] == ["005930"]


def test_binance_reselection_scheduler_does_not_block_trading_cycle():
    from trading.trader import Trader

    started = threading.Event()
    release = threading.Event()
    trader = object.__new__(Trader)
    trader._coin_reselection_lock = threading.RLock()
    trader._coin_reselection_thread = None
    trader._pending_regime_reselection = "bull"
    trader.last_coin_selection_time = 0.0
    trader.logger = logging.getLogger("binance-selection-scheduler")

    def reselect():
        started.set()
        release.wait(1)
        return True

    trader._reselect_coins = reselect
    before = time.monotonic()
    assert Trader._schedule_reselect_coins(trader) is True
    assert time.monotonic() - before < 0.2
    assert started.wait(1)
    assert Trader._schedule_reselect_coins(trader) is False
    release.set()
    trader._coin_reselection_thread.join(1)

    assert trader.last_coin_selection_time > 0
    assert trader._pending_regime_reselection == ""


def test_unified_reselection_scheduler_is_independent_per_exchange():
    from trading.unified_trader import UnifiedTrader

    releases = {"upbit": threading.Event(), "okx": threading.Event()}
    started = []
    trader = object.__new__(UnifiedTrader)
    trader._coin_reselection_lock = threading.RLock()
    trader._coin_reselection_threads = {}
    trader._pending_regime_reselection_by_exchange = {"upbit": "bull", "okx": "bear"}
    trader.last_coin_selection_time_by_exchange = {}
    trader.logger = logging.getLogger("unified-selection-scheduler")

    def reselect(venue):
        started.append(venue)
        releases[venue].wait(1)
        return True

    trader._reselect_coins_unified = reselect
    assert UnifiedTrader._schedule_reselect_coins_unified(trader, "upbit") is True
    assert UnifiedTrader._schedule_reselect_coins_unified(trader, "okx") is True
    deadline = time.monotonic() + 1
    while len(started) < 2 and time.monotonic() < deadline:
        time.sleep(0.005)
    assert set(started) == {"upbit", "okx"}
    assert UnifiedTrader._schedule_reselect_coins_unified(trader, "upbit") is False
    for event in releases.values():
        event.set()
    for thread in trader._coin_reselection_threads.values():
        thread.join(1)

    assert set(trader.last_coin_selection_time_by_exchange) == {"upbit", "okx"}
    assert trader._pending_regime_reselection_by_exchange == {}
