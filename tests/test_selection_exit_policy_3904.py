from trading.exit_policy import (
    build_exit_policy,
    format_exit_policy,
    record_insurance_submission,
)
from trading.selection_policy import (
    SelectionPolicy,
    StrategyUniversePolicy,
    combine_selection_paths,
    resolve_effective_market_regime,
    select_advanced_strategy_universe,
)
from trading.stock_exit_policy import resolve_stock_exit_thresholds
from trading.trade_candidate import evaluate_trade_candidate


def test_selection_policy_keeps_pinned_first_and_fills_with_auto_candidates():
    selected = SelectionPolicy(
        target="binance",
        asset_class="crypto",
        limit=3,
    ).resolve(
        pinned_symbols=["XRPUSDT"],
        automatic_candidates=[
            {"symbol": "BTCUSDT", "score": 90},
            {"symbol": "XRPUSDT", "score": 80},
            {"symbol": "ETHUSDT", "score": 70},
        ],
    )

    assert [item["symbol"] for item in selected] == [
        "XRPUSDT",
        "BTCUSDT",
        "ETHUSDT",
    ]
    assert selected[0]["_selection_source"] == "user_pinned"
    assert selected[1]["_selection_source"] == "auto_market"


def test_selection_policy_does_not_silently_drop_explicit_pins_over_limit():
    selected = SelectionPolicy(
        target="kiwoom",
        asset_class="stock",
        limit=2,
    ).resolve(
        pinned_symbols=["005930", "000660", "035420"],
        automatic_candidates=["069500"],
    )
    assert [item["symbol"] for item in selected] == ["005930", "000660", "035420"]


def test_explicit_symbol_regime_scope_uses_symbol_regime_for_custom_strategy():
    strategy = {
        "id": "bull-id",
        "name": "상승장 전략",
        "priority": 10,
        "target_scope": "exchange:binance",
        "market_regimes": ["bull"],
        "regime_scope": "symbol",
        "signal_mode": "independent",
        "entry_signal": "LONG",
        "engine_settings": {"tp_percent": 0.02, "sl_percent": 0.01},
        "rules": {
            "signal_mode": "independent",
            "entry_signal": "LONG",
            "executable_entry": {"all": []},
        },
    }
    candidate = evaluate_trade_candidate(
        symbol="BTCUSDT",
        context={"signal": "HOLD", "trend_direction": "UPTREND"},
        strategy_pool=[strategy],
        asset_class="crypto",
        target="binance",
        market_regime="bear",
    )

    assert candidate.allowed is True
    assert candidate.market_regime == "bull"
    assert candidate.strategy_name == "상승장 전략"
    assert candidate.evaluation["market_regime_source"] == "context:trend_direction"


def test_explicit_symbol_regime_resolution_reports_source():
    assert resolve_effective_market_regime(
        {"symbol_market_regime": "DOWNTREND"},
        "bull",
        "symbol",
    ) == ("bear", "context:symbol_market_regime")


def test_default_regime_scope_uses_overall_market_not_symbol_trend():
    assert resolve_effective_market_regime(
        {"symbol_market_regime": "bull"},
        "bear",
    ) == ("bear", "target_fallback")


def test_strategy_universe_policy_filters_locally_and_preserves_pinned_symbol():
    policy = StrategyUniversePolicy.from_mapping({
        "exclude_symbols": ["BADUSDT"],
        "min_quote_volume": 1_000_000,
        "max_spread_bps": 20,
        "min_volatility_percent": 0.5,
        "max_volatility_percent": 5.0,
        "max_candidates": 2,
    })
    result = policy.resolve(
        market_candidates=[
            {"symbol": "BTCUSDT", "quoteVolume": 5_000_000, "spread_bps": 5, "volatility": 1.2},
            {"symbol": "ETHUSDT", "quoteVolume": 4_000_000, "spread_bps": 8, "volatility": 2.0},
            {"symbol": "LOWUSDT", "quoteVolume": 10_000, "spread_bps": 4, "volatility": 1.0},
            {"symbol": "BADUSDT", "quoteVolume": 8_000_000, "spread_bps": 2, "volatility": 1.0},
        ],
        pinned_symbols=["LOWUSDT"],
        strategy_id="v1",
    )

    assert [item["symbol"] for item in result] == ["LOWUSDT", "BTCUSDT"]
    assert result[0]["_force_evaluate"] is True
    assert all(item["_selection_pipeline"] == "advanced" for item in result)


def test_general_and_advanced_selection_paths_are_combined_without_duplicates():
    combined = combine_selection_paths(
        [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}],
        [{"symbol": "BTCUSDT", "_eligible_strategy_ids": ["v1"]}, {"symbol": "SOLUSDT"}],
    )
    assert [item["symbol"] for item in combined] == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    assert combined[0]["_selection_pipeline"] == "general+advanced"
    assert combined[0]["_eligible_strategy_modes"] == ["confirm", "independent"]
    assert combined[2]["_eligible_strategy_modes"] == ["independent"]


def test_only_independent_strategy_contributes_strategy_universe():
    pool = [
        {
            "id": "confirm",
            "signal_mode": "confirm",
            "target_scope": "exchange:okx",
            "rules": {"universe_policy": {"include_symbols": ["XRPUSDT"]}},
        },
        {
            "id": "independent",
            "signal_mode": "independent",
            "target_scope": "exchange:okx",
            "rules": {
                "universe_policy": {
                    "include_symbols": ["BTCUSDT"],
                    "max_candidates": 3,
                }
            },
        },
    ]
    selected = select_advanced_strategy_universe(
        strategy_pool=pool,
        market_candidates=[{"symbol": "BTCUSDT"}, {"symbol": "XRPUSDT"}],
        pinned_symbols=[],
        asset_class="crypto",
        target="okx",
    )
    assert [item["symbol"] for item in selected] == ["BTCUSDT"]


def test_exit_policy_keeps_fallback_effective_and_submitted_layers_separate():
    policy = build_exit_policy(
        settings={"default_tp": 0.0018, "default_sl": 0.0020},
        exit_plan={"strategy_owned": True, "source": "custom_strategy"},
        effective_tp_fraction=0.02,
        effective_sl_fraction=0.01,
        effective_reason="AI 커스텀 전략 원형",
        entry_price=100.0,
        side="LONG",
        asset_class="crypto",
        target="binance",
        symbol="BTCUSDT",
    )
    submitted = record_insurance_submission(
        policy,
        submitted_tp_price=102.0,
        submitted_sl_price=99.0,
        status="verified_on_exchange",
        order_ids={"tp": "1", "sl": "2"},
    )

    assert submitted["unit"] == "fraction"
    assert submitted["fallback"]["tp_fraction"] == 0.0018
    assert submitted["effective"]["tp_fraction"] == 0.02
    assert submitted["insurance"]["submitted_tp_price"] == 102.0
    assert policy["insurance"]["submitted_tp_price"] == 0.0
    rendered = format_exit_policy(submitted)
    assert "기본폴백" in rendered
    assert "현재적용" in rendered
    assert "보험제출" in rendered


def test_stock_settings_are_converted_to_common_fraction_unit_once():
    thresholds = resolve_stock_exit_thresholds(
        policy={
            "take_profit_percent": 5.0,
            "stop_loss_percent": 8.0,
        },
        is_etf=False,
        market_regime="bull",
    )

    assert thresholds["unit"] == "fraction"
    assert thresholds["fallback_tp_fraction"] == 0.05
    assert thresholds["effective_tp_fraction"] == 0.065
