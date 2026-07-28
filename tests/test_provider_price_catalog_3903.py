from trading.ai.provider_catalog import (
    OFFICIAL_PRICING_URLS,
    PRICE_SNAPSHOT_AS_OF,
    format_provider_price_guide,
    provider_price_rows,
)


def test_price_catalog_covers_every_supported_provider():
    assert set(OFFICIAL_PRICING_URLS) == {"openai", "deepseek", "kimi", "anthropic", "gemini"}
    assert PRICE_SNAPSHOT_AS_OF == "2026-07-28"
    for provider in OFFICIAL_PRICING_URLS:
        assert provider_price_rows(provider)


def test_price_guide_marks_units_date_and_billing_caveat():
    text = format_provider_price_guide("anthropic")
    assert "USD / 100만 토큰" in text
    assert "claude-sonnet-5" in text
    assert "실제 청구" in text
