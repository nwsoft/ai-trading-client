import ast
import threading
from pathlib import Path

from trading.analyzer import Analyzer
from trading.unified_trader import UnifiedTrader


class _ExchangeManagerSpy:
    def __init__(self):
        self.calls = []

    def get_klines(self, symbol, interval, limit, exchange_name=None):
        self.calls.append((symbol, interval, limit, exchange_name))
        return [
            [1_700_000_000_000 + i * 300_000, 1, 2, 0.5, 1.5, 10]
            for i in range(50)
        ]

    def get_current_price(self, symbol, exchange_name=None):
        self.calls.append((symbol, "price", 0, exchange_name))
        return 123.0


def test_analyzer_market_data_uses_requested_exchange_and_isolated_cache():
    manager = _ExchangeManagerSpy()
    analyzer = Analyzer(binance_client=None, exchange_manager=manager)

    analyzer._exchange_context = "bybit"
    assert analyzer.get_market_data("BTC/USDT:USDT")
    analyzer._exchange_context = "bitget"
    assert analyzer.get_market_data("BTC/USDT:USDT")

    assert manager.calls[0][3] == "bybit"
    assert manager.calls[1][3] == "bitget"


def test_analyzer_exchange_context_is_thread_local():
    analyzer = Analyzer(binance_client=None, exchange_manager=_ExchangeManagerSpy())
    barrier = threading.Barrier(2)
    seen = {}

    def worker(exchange):
        analyzer._exchange_context = exchange
        barrier.wait()
        seen[exchange] = analyzer._exchange_context

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("okx", "bybit")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert seen == {"okx": "okx", "bybit": "bybit"}


class _EmptyExchangeManager:
    def get_klines(self, *args, **kwargs):
        return []

    def get_current_price(self, *args, **kwargs):
        return None


class _BinanceMustNotBeUsed:
    def get_klines(self, *args, **kwargs):
        raise AssertionError("non-Binance analysis must not fall back to Binance")

    def get_current_price(self, *args, **kwargs):
        raise AssertionError("non-Binance analysis must not fall back to Binance")


def test_non_binance_empty_data_does_not_cross_fallback_to_binance():
    analyzer = Analyzer(binance_client=_BinanceMustNotBeUsed(), exchange_manager=_EmptyExchangeManager())
    analyzer._exchange_context = "okx"

    assert analyzer._get_klines("BTC/USDT:USDT", "5m", 50) == []
    assert analyzer._get_current_price("BTC/USDT:USDT") is None


class _MarketExchange:
    markets = {
        "BTC/USDT:USDT": {"active": True, "swap": True, "quote": "USDT"},
    }


class _OkxAdapter:
    exchange = _MarketExchange()

    @staticmethod
    def _normalize_symbol(symbol):
        value = str(symbol).upper().replace("-", "").replace("_", "")
        if "/" in str(symbol):
            return symbol if ":" in symbol else f"{symbol}:USDT"
        if value.endswith("USDT"):
            return f"{value[:-4]}/USDT:USDT"
        return symbol


class _UnifiedManager:
    def get_exchange(self, name, trading_type):
        assert name == "okx"
        assert trading_type == "futures"
        return _OkxAdapter()


def test_okx_string_fallback_survives_supported_symbol_prefilter():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.unified_manager = _UnifiedManager()
    trader.logger = type("L", (), {"info": lambda *args, **kwargs: None, "warning": lambda *args, **kwargs: None})()

    filtered = trader._prefilter_supported_coins("okx", ["BTCUSDT"])

    assert filtered == [{"symbol": "BTC/USDT:USDT", "is_major": True}]


def test_binance_cycle_does_not_shadow_module_time_import():
    source = Path("trading/trader.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    cycle = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "execute_trading_cycle"
    )
    local_time_imports = [
        node for node in ast.walk(cycle)
        if isinstance(node, ast.Import) and any(alias.name == "time" and alias.asname is None for alias in node.names)
    ]
    assert local_time_imports == []
