from trading.analyzer import Analyzer
from trading.evaluator import Evaluator
from trading.market_sentiment_analyzer import MarketSentimentAnalyzer


class _BinanceMustNotRun:
    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise AssertionError(f"Binance call leaked into non-Binance context: {name}")
        return _fail


class _ExchangeManager:
    def __init__(self):
        self.calls = []

    def get_klines(self, symbol, interval, limit, exchange_name=None):
        self.calls.append(("klines", symbol, interval, limit, exchange_name))
        return [[i, 1, 2, 0.5, 1.5, 10 + i] for i in range(max(limit, 2))]

    def get_24h_ticker(self, symbol, exchange_name=None):
        self.calls.append(("ticker", symbol, exchange_name))
        return {"volume": 1000, "baseVolume": 1000, "priceChangePercent": 1.0}


def test_evaluator_non_binance_batch_never_uses_binance_client():
    manager = _ExchangeManager()
    analyzer = Analyzer(_BinanceMustNotRun(), exchange_manager=manager)
    evaluator = Evaluator(analyzer, recorder=None, settings={})
    evaluator._set_selection_context("bitget", object())

    result = evaluator._get_multiple_context_klines(
        ["ADA/USDT:USDT"], "15m", 3
    )

    assert list(result) == ["ADA/USDT:USDT"]
    assert manager.calls == [
        ("klines", "ADA/USDT:USDT", "15m", 3, "bitget")
    ]
    assert evaluator._get_funding_rate("ADAUSDT") is None
    assert evaluator._get_open_interest("ADAUSDT") is None
    assert evaluator._analyze_market_activity()["source"] == "neutral_non_binance"


def test_market_sentiment_non_binance_uses_selected_exchange_only():
    manager = _ExchangeManager()
    sentiment = MarketSentimentAnalyzer(
        _BinanceMustNotRun(), exchange_manager=manager
    )

    volume = sentiment.analyze_volume_patterns("BTC/USDT:USDT", "okx")

    assert volume.current_volume == 1000
    assert all(call[-1] == "okx" for call in manager.calls)
    assert sentiment.get_funding_rate_analysis("BTCUSDT", "okx").current_rate == 0
    assert sentiment.get_open_interest_analysis("BTCUSDT", "okx") is None
    assert sentiment.get_long_short_ratio("BTCUSDT", "okx") is None


def test_tokenized_stock_denylist_covers_reported_bitget_symbols():
    source = __import__("pathlib").Path("trading/market_asset_classifier.py").read_text(encoding="utf-8")
    for base in ("AAOI", "CRCL", "EPIC", "MU", "MUU", "SKHYNIX", "SPCX"):
        assert f'"{base}"' in source


def test_unified_execution_has_no_flat_global_coin_fallback():
    source = __import__("pathlib").Path("trading/unified_trader.py").read_text(encoding="utf-8")
    execution_section = source.split("# 1. 거래소별 선택 코인 사용", 1)[1].split(
        "# Evaluator의 극한 폴백", 1
    )[0]
    assert "selected_coins_by_exchange" in execution_section
    assert "isinstance(selected_store, list)" not in execution_section
    assert "legacy_selected" not in execution_section
    assert "main_app', None), 'selected_coins'" not in execution_section
