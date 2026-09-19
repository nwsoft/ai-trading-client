from __future__ import annotations

from trading.parallel_strategy_paper import ParallelStrategyPaperEngine


def _strategy(*, version="v1", direction="LONG", target_scope="asset:crypto"):
    return {
        "id": version,
        "name": "parallel-test",
        "strategy_key": "strategy_parallel",
        "version_id": version,
        "strategy_scope": "unified",
        "operation_mode": "paper_validation",
        "signal_mode": "independent",
        "entry_signal": direction,
        "target_scope": target_scope,
        "market_regimes": ["all"],
        "rules": {"executable_entry": {}},
        "engine_settings": {
            "tp_percent": 0.01,
            "sl_percent": 0.01,
            "_unit": "fraction",
            "leverage": 2,
        },
    }


def _settings():
    return {
        "paper_trading": False,
        "min_trade_amount": 20.0,
        "parallel_strategy_paper_validation": {
            "enabled": True,
            "max_strategies_per_venue": 3,
        },
        "position_sizing_policy": {
            "mode": "fixed_notional",
            "paper_equity_usdt": 1000.0,
            "paper_equity_krw": 1_000_000.0,
        },
    }


def test_parallel_paper_opens_and_closes_without_any_venue_client(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    recorded = []
    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        module, "record_paper_strategy_outcome",
        lambda **kwargs: recorded.append(kwargs) or kwargs,
    )
    settings = _settings()
    engine = ParallelStrategyPaperEngine(settings_provider=lambda: settings)

    opened = engine.observe(
        target="binance", symbol="BTCUSDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy()], market_regime="range",
    )
    closed = engine.observe(
        target="binance", symbol="BTCUSDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "HOLD", "current_price": 102.0},
        strategy_pool=[_strategy()], market_regime="range",
    )

    assert opened == {"evaluated": 1, "opened": 1, "closed": 0}
    assert closed == {"evaluated": 1, "opened": 0, "closed": 1}
    assert not engine.snapshot()
    assert recorded[0]["strategy_key"] == "strategy_parallel"
    assert recorded[0]["version_id"] == "v1"
    assert recorded[0]["exchange"] == "binance"
    assert recorded[0]["net_pnl"] < recorded[0]["gross_pnl"]


def test_completed_strategy_still_closes_existing_virtual_position(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module
    recorded = []
    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "record_paper_strategy_outcome", lambda **kw: recorded.append(kw))
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    common = dict(target="binance", symbol="BTCUSDT", asset_class="crypto",
                  primary_execution_mode="live", market_regime="range")
    assert engine.observe(**common, context={"signal": "LONG", "current_price": 100},
                          strategy_pool=[_strategy()])["opened"] == 1
    # Reload also proves frozen exit ownership survives restart and revocation.
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    result = engine.observe(**common, context={"signal": "LONG", "current_price": 102}, strategy_pool=[])
    assert result == {"evaluated": 1, "opened": 0, "closed": 1}
    assert len(recorded) == 1
    assert engine.observe(**common, context={"signal": "LONG", "current_price": 102},
                          strategy_pool=[])["opened"] == 0


def test_parallel_paper_is_disabled_in_global_paper_mode(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    settings = _settings()
    settings["paper_trading"] = True
    engine = ParallelStrategyPaperEngine(settings_provider=lambda: settings)
    result = engine.observe(
        target="binance", symbol="BTCUSDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy()], market_regime="range",
    )
    assert result == {"evaluated": 0, "opened": 0, "closed": 0}


def test_krw_spot_and_stocks_never_open_short(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    for target, asset_class, scope in (
        ("upbit", "crypto", "asset:crypto"),
        ("bithumb", "crypto", "asset:crypto"),
        ("coinone", "crypto", "asset:crypto"),
        ("kiwoom", "stock", "asset:stock"),
        ("shinhan", "etf", "asset:etf"),
    ):
        result = engine.observe(
            target=target, symbol="TEST", asset_class=asset_class,
            primary_execution_mode="live_api",
            context={"signal": "SHORT", "current_price": 100.0},
            strategy_pool=[_strategy(direction="SHORT", target_scope=scope)],
            market_regime="range",
        )
        assert result["opened"] == 0
    assert not engine.snapshot()


def test_coinone_parallel_paper_uses_krw_spot_lifecycle_without_venue_orders(
    tmp_path, monkeypatch
):
    import trading.parallel_strategy_paper as module

    recorded = []
    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        module, "record_paper_strategy_outcome",
        lambda **kwargs: recorded.append(kwargs) or kwargs,
    )
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)

    opened = engine.observe(
        target="coinone", symbol="BTC/KRW", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100_000_000.0},
        strategy_pool=[_strategy()], market_regime="bull",
    )
    closed = engine.observe(
        target="coinone", symbol="BTC/KRW", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "HOLD", "current_price": 102_000_000.0},
        strategy_pool=[_strategy()], market_regime="bull",
    )

    assert opened == {"evaluated": 1, "opened": 1, "closed": 0}
    assert closed == {"evaluated": 1, "opened": 0, "closed": 1}
    assert recorded[0]["exchange"] == "coinone"
    assert recorded[0]["quote_currency"] == "KRW"
    assert recorded[0]["net_pnl"] < recorded[0]["gross_pnl"]


def test_strategy_versions_have_independent_virtual_positions(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    result = engine.observe(
        target="okx", symbol="ETH/USDT:USDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy(version="v1"), _strategy(version="v2")],
        market_regime="range",
    )
    assert result["opened"] == 2
    assert {row["version_id"] for row in engine.snapshot()} == {"v1", "v2"}


def test_parallel_paper_does_not_run_beside_learning(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    result = engine.observe(
        target="okx", symbol="ETH/USDT:USDT", asset_class="crypto",
        primary_execution_mode="learning",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy()], market_regime="range",
    )
    assert result == {"evaluated": 0, "opened": 0, "closed": 0}


def test_parallel_futures_uses_runtime_contract_size(tmp_path, monkeypatch):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    result = engine.observe(
        target="okx", symbol="BTC/USDT:USDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0, "_contract_size": 0.01},
        strategy_pool=[_strategy()], market_regime="range",
    )
    assert result["opened"] == 1
    position = engine.snapshot()[0]
    assert position["contract_size"] == 0.01
    assert position["quantity"] == 20.0


def test_parallel_paper_does_not_reuse_one_strategy_budget_across_symbols(
    tmp_path, monkeypatch
):
    import trading.parallel_strategy_paper as module

    monkeypatch.setattr(module, "get_app_data_dir", lambda: tmp_path)
    engine = ParallelStrategyPaperEngine(settings_provider=_settings)
    first = engine.observe(
        target="bybit", symbol="BTC/USDT:USDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy()], market_regime="range",
    )
    second = engine.observe(
        target="bybit", symbol="ETH/USDT:USDT", asset_class="crypto",
        primary_execution_mode="live",
        context={"signal": "LONG", "current_price": 100.0},
        strategy_pool=[_strategy()], market_regime="range",
    )

    assert first["opened"] == 1
    assert second["opened"] == 0
    assert len(engine.snapshot()) == 1


def test_live_runtime_keeps_active_and_paper_validation_pools_separate():
    from types import SimpleNamespace
    from web_platform.headless_runtime import HeadlessTradingRuntime

    active = {**_strategy(version="active"), "operation_mode": "standard"}
    paper = _strategy(version="paper")

    class Customizer:
        def get_active_strategy_pool(self):
            return [active]

        def get_paper_strategy_pool(self):
            return [active, paper]

    runtime = object.__new__(HeadlessTradingRuntime)
    runtime.settings = {
        "paper_trading": False,
        "ai_custom_runtime": {"enabled": True},
        "parallel_strategy_paper_validation": {"enabled": True},
    }
    runtime.strategy_customizer = Customizer()
    runtime.strategy_customizer_unified = Customizer()
    runtime.trader = SimpleNamespace()
    runtime.unified_trader = SimpleNamespace()
    runtime.parallel_strategy_paper = object()

    pool = runtime.sync_custom_strategy_runtime_pools()

    assert [item["version_id"] for item in pool] == ["active"]
    assert [item["version_id"] for item in runtime.paper_validation_strategy_pool] == ["paper"]
    for trade_engine in (runtime.trader, runtime.unified_trader):
        assert [item["version_id"] for item in trade_engine.active_custom_strategy_pool] == ["active"]
        assert [item["version_id"] for item in trade_engine.paper_validation_strategy_pool] == ["paper"]


def test_strategy_studio_explains_parallel_live_paper_states():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "webui/src/components/StrategyStudio.tsx").read_text(
        encoding="utf-8"
    )

    assert 'valueOf("parallel_strategy_paper_validation.enabled", false)' in source
    assert "현재 앱은 LIVE이며 독립 PAPER 병행검증이 켜져 있습니다." in source
    assert "현재 앱은 LIVE이며 독립 PAPER 병행검증이 꺼져 있어 등록 후 대기합니다." in source
    assert "전략·버전·거래소별 가상자금·포지션·원장을 분리합니다." in source
    assert "거래소 주문 API를 소유하지 않으며 검증 통과도 자동 LIVE 적용되지 않습니다." in source
