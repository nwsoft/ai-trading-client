from trading.spot_position_policy import (
    assess_spot_holding,
    balance_quantity,
    safe_managed_close_quantity,
    spot_base_asset,
    summarize_spot_portfolio,
)


def test_spot_symbol_formats_resolve_same_base_asset():
    assert spot_base_asset("KRW-SNX") == "SNX"
    assert spot_base_asset("SNX/KRW") == "SNX"
    assert spot_base_asset("SNXKRW") == "SNX"


def test_small_residual_is_dust_and_does_not_become_managed_position():
    assessment = assess_spot_holding({"SNX": 4.4595}, "SNX/KRW", 319)
    assert assessment.classification == "dust"
    assert assessment.notional < 5000


def test_material_unmanaged_holding_is_detected_before_entry():
    assessment = assess_spot_holding({"GWEI": {"total": 200}}, "KRW-GWEI", 31.86)
    assert assessment.is_material is True
    assert assessment.notional == 6372


def test_close_never_sells_preexisting_dust_or_more_than_managed_amount():
    assert safe_managed_close_quantity(
        managed_quantity=100,
        actual_quantity=104.5,
        baseline_quantity=4.5,
    ) == 100
    assert safe_managed_close_quantity(
        managed_quantity=100,
        actual_quantity=84.5,
        baseline_quantity=4.5,
    ) == 80
    assert balance_quantity({"PYR": {"free": "12.2248"}}, "PYR") == 12.2248


def test_total_position_risk_counts_material_holdings_but_not_dust():
    summary = summarize_spot_portfolio(
        {"KRW": 90_000, "GWEI": 88.0064, "SNX": 4.4595, "BTC": 0.01},
        {"GWEI": 31.86, "SNX": 319, "BTC": 100_000_000},
    )
    assert summary.material_assets == {"BTC"}
    assert summary.dust_assets == {"GWEI", "SNX"}


def test_managed_assets_are_not_double_counted_in_total_risk_slots():
    summary = summarize_spot_portfolio(
        {"KRW": 10_000, "BTC": 0.01},
        {"BTC": 100_000_000},
        managed_assets={"BTC"},
    )
    assert not summary.material_assets
