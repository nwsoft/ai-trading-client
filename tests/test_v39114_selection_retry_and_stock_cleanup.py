from types import SimpleNamespace

from trading.exchanges.adapters.mirae_asset_stock_adapter import MiraeAssetStockAdapter
from trading.exchanges.adapters.shinhan_stock_adapter import ShinhanStockAdapter
from trading.selection_policy import has_executable_candidates
from trading.trader import Trader
from trading.unified_trader import UnifiedTrader


class _ClosableHttp:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_visible_only_fallback_has_no_executable_candidates():
    assert has_executable_candidates(
        [{"symbol": "BTCUSDT", "selection_status": "fallback_unscored"}]
    ) is False
    assert has_executable_candidates(
        [
            {"symbol": "BTCUSDT", "selection_status": "fallback_unscored"},
            {"symbol": "ETHUSDT", "selection_status": "scored_partial"},
        ]
    ) is True


def test_binance_failed_refresh_preserves_previous_scored_universe():
    old = [{"symbol": "ETHUSDT", "selection_status": "scored", "overall_score": 77.0}]
    fallback = [{"symbol": "BTCUSDT", "selection_status": "fallback_unscored"}]

    class MainApp:
        selected_coins = list(old)

        def select_trading_coins(self):
            self.selected_coins = list(fallback)

    trader = Trader.__new__(Trader)
    trader.main_app = MainApp()
    trader.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    trader.log_event = lambda *args, **kwargs: None
    trader._analyze_market_regime_binance = lambda: "normal"

    assert trader._reselect_coins() is False
    assert trader.main_app.selected_coins == old


def test_binance_fallback_to_fallback_is_not_marked_completed():
    fallback = [{"symbol": "BTCUSDT", "selection_status": "fallback_unscored"}]

    class MainApp:
        selected_coins = list(fallback)

        def select_trading_coins(self):
            self.selected_coins = list(fallback)

    trader = Trader.__new__(Trader)
    trader.main_app = MainApp()
    trader.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    trader.log_event = lambda *args, **kwargs: None
    trader._analyze_market_regime_binance = lambda: "normal"

    assert trader._reselect_coins() is False


def test_unified_failed_refresh_preserves_previous_scored_universe():
    old = [{"symbol": "ETH/USDT:USDT", "selection_status": "scored", "overall_score": 77.0}]
    fallback = [{"symbol": "BTC/USDT:USDT", "selection_status": "fallback_unscored"}]
    main_app = SimpleNamespace(
        current_exchange="okx",
        selected_coins=[],
        selected_coins_by_exchange={"okx": list(old)},
    )
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.selected_coins = {"okx": list(old)}
    trader.main_app = main_app
    trader.logger = SimpleNamespace(
        info=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
    )
    trader._evaluate_current_market_conditions_unified = lambda *args: "normal"

    def select(exchange_name):
        trader.selected_coins[exchange_name] = list(fallback)
        main_app.selected_coins_by_exchange[exchange_name] = list(fallback)
        main_app.selected_coins = list(fallback)
        return list(fallback)

    trader.select_trading_coins_unified = select

    assert trader._reselect_coins_unified("okx") is False
    assert trader.selected_coins["okx"] == old
    assert main_app.selected_coins_by_exchange["okx"] == old
    assert main_app.selected_coins == old


def test_unscored_retry_uses_cooldown_and_existing_singleflight_scheduler(monkeypatch):
    calls = []
    trader = Trader.__new__(Trader)
    trader.settings = {"coin_selection_failure_retry_seconds": 60}
    trader._last_unscored_reselection_request = 0.0
    trader.main_app = SimpleNamespace(
        evaluator=SimpleNamespace(
            invalidate_selection_cache=lambda venue: calls.append(f"invalidate:{venue}")
        )
    )
    trader._schedule_reselect_coins = lambda: calls.append("binance") or True
    monkeypatch.setattr("trading.trader.time.time", lambda: 1_000.0)

    assert trader._schedule_unscored_reselection() is True
    assert trader._schedule_unscored_reselection() is False
    assert calls == ["invalidate:binance", "binance"]


def test_unified_unscored_retry_uses_bounded_exponential_backoff(monkeypatch):
    calls = []
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {
        "coin_selection_failure_retry_seconds": 60,
        "coin_selection_failure_retry_max_seconds": 900,
    }
    trader._last_unscored_reselection_request_by_exchange = {}
    trader._unscored_reselection_attempts_by_exchange = {}
    trader._schedule_reselect_coins_unified = lambda venue: calls.append(venue) or True
    now = {"value": 1_000.0}
    monkeypatch.setattr("trading.unified_trader.time.time", lambda: now["value"])

    assert trader._schedule_unscored_reselection_unified("okx") is True
    now["value"] = 1_061.0
    assert trader._schedule_unscored_reselection_unified("okx") is False
    now["value"] = 1_121.0
    assert trader._schedule_unscored_reselection_unified("okx") is True

    assert calls == ["okx", "okx"]
    assert trader._unscored_reselection_attempts_by_exchange["okx"] == 2


def test_binance_unscored_universe_skips_regime_work_until_recovery():
    events = []
    trader = Trader.__new__(Trader)
    trader.main_app = SimpleNamespace(
        selected_coins=[
            {
                "symbol": "BTCUSDT",
                "selection_status": "fallback_unscored",
                "execution_eligible": False,
            }
        ]
    )
    trader.settings = {}
    trader.log_event = lambda category, message, **kwargs: events.append((category, message))
    trader._analyze_market_regime_binance_fast = lambda: (_ for _ in ()).throw(
        AssertionError("fallback candidates must not trigger market-regime work")
    )

    assert trader._check_and_reselect_coins_optimized() is None
    assert any("후보 복구 단계" in message for _, message in events)


def test_unified_unscored_retry_is_isolated_per_exchange(monkeypatch):
    calls = []
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.settings = {"coin_selection_failure_retry_seconds": 60}
    trader._last_unscored_reselection_request_by_exchange = {}
    trader._schedule_reselect_coins_unified = lambda venue: calls.append(venue) or True
    monkeypatch.setattr("trading.unified_trader.time.time", lambda: 1_000.0)

    assert trader._schedule_unscored_reselection_unified("OKX") is True
    assert trader._schedule_unscored_reselection_unified("okx") is False
    assert trader._schedule_unscored_reselection_unified("bitget") is True
    assert calls == ["okx", "bitget"]


def test_shinhan_disconnect_closes_read_only_session_and_clears_tokens():
    http = _ClosableHttp()
    adapter = ShinhanStockAdapter("user", "password", backend_client=http)
    adapter.is_connected = True
    adapter._access_token = "secret"
    adapter._token_expires_at = 99.0

    assert adapter.disconnect() is True
    assert http.closed is True
    assert adapter._http is None
    assert adapter._access_token == ""
    assert adapter._token_expires_at == 0.0
    assert adapter.is_connected is False


def test_mirae_and_kis_base_disconnect_closes_read_only_session():
    http = _ClosableHttp()
    adapter = MiraeAssetStockAdapter("user", "password", backend_client=http)
    adapter.is_connected = True
    adapter._access_token = "secret"

    assert adapter.disconnect() is True
    assert http.closed is True
    assert adapter._http is None
    assert adapter._access_token == ""
    assert adapter.is_connected is False
