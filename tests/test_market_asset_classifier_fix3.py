from trading.market_asset_classifier import is_crypto_derivative_candidate


def _market(base="BTC", **overrides):
    market = {
        "active": True,
        "swap": True,
        "future": False,
        "contract": True,
        "base": base,
        "quote": "USDT",
        "info": {},
    }
    market.update(overrides)
    return market


def test_regular_crypto_usdt_swap_is_allowed():
    assert is_crypto_derivative_candidate(_market("BTC")) is True


def test_reported_tokenized_stock_is_blocked_even_without_metadata():
    assert is_crypto_derivative_candidate(_market("CRCL")) is False


def test_new_equity_contract_is_blocked_by_exchange_metadata():
    assert is_crypto_derivative_candidate(
        _market("NEWCO", info={"category": "Tokenized Stock"})
    ) is False


def test_index_commodity_and_forex_metadata_are_blocked():
    for product_type in ("INDEX", "Commodity Futures", "FX"):
        assert is_crypto_derivative_candidate(
            _market("SYNTH", productType=product_type)
        ) is False


def test_user_exclusion_and_non_usdt_or_spot_are_blocked():
    assert is_crypto_derivative_candidate(
        _market("MEME"), configured_exclusions=["meme"]
    ) is False
    assert is_crypto_derivative_candidate(_market("BTC", quote="USDC")) is False
    assert is_crypto_derivative_candidate(
        _market("BTC", swap=False, future=False, contract=False)
    ) is False
