from trading.unified_trader import UnifiedTrader


def test_selected_exchange_trades_while_other_enabled_exchanges_learn_only():
    trader = UnifiedTrader(
        settings={
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "bybit", "okx", "bitget"],
            "trade_enabled_exchanges": [],
            "learning_enabled_exchanges": [],
        },
        exchange_manager=None,
        unified_manager=None,
    )

    assert trader.trade_enabled_exchanges == ["binance"]
    assert set(trader.learning_enabled_exchanges) == {"binance", "bybit", "okx", "bitget"}
    assert trader._is_trade_enabled("bybit") is False


def test_explicit_multi_exchange_trade_scope_is_respected():
    trader = UnifiedTrader(
        settings={
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "bybit", "okx"],
            "trade_enabled_exchanges": ["bybit", "okx"],
            "learning_enabled_exchanges": ["binance", "bybit", "okx"],
        },
        exchange_manager=None,
        unified_manager=None,
    )

    assert trader.trade_enabled_exchanges == ["bybit", "okx"]
    assert trader._is_trade_enabled("bybit") is True
    assert trader._is_trade_enabled("binance") is False
