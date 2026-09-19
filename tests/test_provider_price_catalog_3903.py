from trading.ai.provider_catalog import (
    OFFICIAL_PRICING_URLS,
    PRICE_SNAPSHOT_AS_OF,
    format_provider_price_guide,
    model_catalog_details,
    provider_price_rows,
)


def test_price_catalog_covers_every_supported_provider():
    assert set(OFFICIAL_PRICING_URLS) == {"openai", "deepseek", "kimi", "anthropic", "gemini"}
    assert PRICE_SNAPSHOT_AS_OF == "2026-09-11"
    for provider in OFFICIAL_PRICING_URLS:
        assert provider_price_rows(provider)


def test_price_guide_marks_units_date_and_billing_caveat():
    text = format_provider_price_guide("anthropic")
    assert "USD / 100만 토큰" in text
    assert "claude-sonnet-5" in text
    assert "실제 청구" in text


def test_model_catalog_exposes_current_chat_and_transcription_routes_with_boundaries():
    openai = {row["model"]: row for row in model_catalog_details("openai")}
    anthropic = {row["model"]: row for row in model_catalog_details("anthropic")}
    gemini = {row["model"]: row for row in model_catalog_details("gemini")}

    assert openai["gpt-6-astra"]["status"] == "recommended"
    assert "transcribe" in openai["gpt-4o-mini-transcribe"]["capabilities"]
    assert anthropic["claude-fable-5-1"]["input_per_mtok_usd"] == 10.0
    assert anthropic["claude-fable-5"]["status"] == "deprecated"
    assert gemini["gemini-3.8-flash"]["output_per_mtok_usd"] == 3.75
    assert all(row["strength"] and row["limitation"] for row in openai.values())
