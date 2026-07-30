from trading.unified_trader import UnifiedTrader


def test_explicit_empty_trade_scope_disables_live_orders():
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

    assert trader.trade_enabled_exchanges == []
    assert set(trader.learning_enabled_exchanges) == {"binance", "bybit", "okx", "bitget"}
    assert trader._is_trade_enabled("bybit") is False
    assert trader._is_trade_enabled("binance") is False


def test_legacy_profile_without_confirmation_is_fail_closed():
    trader = UnifiedTrader(
        settings={
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "bybit"],
        },
        exchange_manager=None,
        unified_manager=None,
    )

    assert trader.trade_enabled_exchanges == []


def test_explicit_multi_exchange_trade_scope_is_respected():
    trader = UnifiedTrader(
        settings={
            "selected_exchange": "binance",
            "enabled_exchanges": ["binance", "bybit", "okx"],
            "trade_enabled_exchanges": ["bybit", "okx"],
            "_trade_scope_user_confirmed_v3904": True,
            "learning_enabled_exchanges": ["binance", "bybit", "okx"],
        },
        exchange_manager=None,
        unified_manager=None,
    )

    assert trader.trade_enabled_exchanges == ["bybit", "okx"]
    assert trader._is_trade_enabled("bybit") is True
    assert trader._is_trade_enabled("binance") is False
