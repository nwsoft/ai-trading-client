"""Common client contracts: historical performance never grants LIVE permission."""
from copy import deepcopy
import pytest

from trading.custom_strategy_pipeline import CustomStrategyPipeline
from trading.custom_strategy_validator import historical_quality_assessment
from test_v39147_strategy_repair import compiled


@pytest.mark.parametrize("count,pnl,dd,status,passed", [
    (0, 0, 0, "no_trades", False),
    (1, 2, 0, "insufficient_sample", False),
    (3, -1, 2, "completed", False),
    (3, 1, 11, "completed", False),
    (3, 1, 10, "completed", True),
    (3, None, 0, "unavailable", False),
    (3, float("nan"), 0, "unavailable", False),
    (3, 1, float("inf"), "unavailable", False),
    (True, 1, 0, "unavailable", False),
])
def test_quality_categories(count, pnl, dd, status, passed):
    metrics = {"decisions": count, "net_pnl_percent": pnl, "max_drawdown_percent": dd}
    result = historical_quality_assessment(metrics)
    assert result["assessment_status"] == status
    assert result["quality_passed"] is passed
    assert "guardrail_violations" not in result
    if count == 0:
        assert result["quality_reasons"] == ["sample_too_small"]


@pytest.mark.parametrize("scope", ["exchange:binance", "exchange:okx", "asset:stock"])
@pytest.mark.parametrize("legacy", [False, True])
def test_rejected_replay_survives_restart_and_can_start_paper_without_live(tmp_path, scope, legacy):
    rules = compiled()
    # Explicit manual fixture, not an automatic migration of source-backed rules.
    rules.pop("source_grounding", None)
    rules.pop("source_evidence", None)
    rules["target_scope"] = scope
    pipeline = CustomStrategyPipeline(storage_path=tmp_path / "strategies.json")
    row = pipeline.submit(name="old-or-new", rules=rules)
    key, vid = row["strategy_key"], row["version_id"]
    pipeline.approve(key, vid, approved_by="fixture")
    metrics = {"decisions": 4, "net_pnl_percent": -2, "max_drawdown_percent": 3}
    if not legacy:
        metrics.update(historical_quality_assessment(metrics))
    row = pipeline.record_execution_validation(key, vid, decisions=4,
        guardrail_violations=1 if legacy else 0, metrics=metrics, mode="historical_replay")
    assert row["status"] == "execution_rejected"
    before = deepcopy(row)
    disk = (tmp_path / "strategies.json").read_bytes()
    loaded = CustomStrategyPipeline(storage_path=tmp_path / "strategies.json")
    assert (tmp_path / "strategies.json").read_bytes() == disk
    row = loaded.get_version(key, vid)
    assert row["execution_validation"] == before["execution_validation"]
    with pytest.raises(ValueError):
        loaded.activate(key, vid, live_confirmation=True)
    paper = loaded.start_paper_observation(key, vid)
    assert paper["status"] == "paper_observing"
    assert paper["rules"] == before["rules"]
    assert paper["execution_validation"] == before["execution_validation"]
    assert paper["ir_hash"] == before["ir_hash"]
    assert not loaded.active_versions


def test_missing_source_entry_stays_blocked_and_draft_preserved(tmp_path):
    rules = compiled()
    rules["executable_entry"] = {"all": [], "any": []}
    pipeline = CustomStrategyPipeline(storage_path=tmp_path / "strategies.json")
    row = pipeline.submit(name="incomplete old source", rules=rules)
    original = deepcopy(row["rules"])
    with pytest.raises(ValueError):
        pipeline.start_paper_observation(row["strategy_key"], row["version_id"])
    assert pipeline.get_version(row["strategy_key"], row["version_id"])["rules"] == original
    assert not pipeline.active_versions and not pipeline.paper_versions


def test_historical_pass_does_not_grant_standard_live(tmp_path):
    pipeline = CustomStrategyPipeline(storage_path=tmp_path / "strategies.json")
    row = pipeline.submit(name="passed", rules=compiled())
    key, vid = row["strategy_key"], row["version_id"]
    pipeline.approve(key, vid, approved_by="fixture")
    metrics = {"decisions": 3, "net_pnl_percent": 2, "max_drawdown_percent": 0}
    metrics.update(historical_quality_assessment(metrics))
    result = pipeline.record_execution_validation(key, vid, decisions=3, metrics=metrics, mode="historical_replay")
    assert result["execution_validation"]["passed"]
    with pytest.raises(ValueError, match="PAPER"):
        pipeline.activate(key, vid, live_confirmation=True)
    assert not pipeline.active_versions


@pytest.mark.parametrize("dated", [False, True])
@pytest.mark.parametrize("source", ["binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget", "kis", "kiwoom", "shinhan", "mirae"])
def test_real_service_zero_signal_replay_to_paper_all_venues(tmp_path, monkeypatch, source, dated):
    import web_platform.application_services as services_module
    from web_platform.application_services import ApplicationServices
    from web_platform.contracts import CandleContract, CandleSnapshotContract

    stock = source in {"kis", "kiwoom", "shinhan", "mirae"}
    interval = "1d" if stock else "15m"
    market = "spot" if stock or source in {"upbit", "bithumb", "coinone"} else "futures"
    symbol = "005930" if stock else "BTCUSDT"
    step = 86400000 if stock else 900000

    def snapshot(*args, **kwargs):
        candles = [CandleContract(source=source, market_type=market, symbol=symbol, interval=interval,
            open_time=1700000000000+i*step, close_time=1700000000000+(i+1)*step-1,
            open=100+i, high=102+i, low=99+i, close=101+i, volume=1000,
            closed=True, sequence=i) for i in range(250)]
        return CandleSnapshotContract(source=source, symbol=symbol, interval=interval, candles=candles)

    class Provider:
        get_candles = staticmethod(snapshot)
        get_candles_range = staticmethod(snapshot)

    monkeypatch.setattr(services_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(services_module, "set_current_user_account", lambda _: None)
    monkeypatch.setattr(services_module, "load_settings", lambda **_: {"enabled_stock_brokers":[source]})
    service = ApplicationServices(account="fixture", historical_market_data=Provider())
    monkeypatch.setattr(service, "stock_candle_snapshot", snapshot)
    rules = compiled()
    rules.pop("source_grounding", None)
    rules.pop("source_evidence", None)
    rules.update(target_scope="asset:stock" if stock else f"exchange:{source}", decision_timeframe=interval)
    scope = "binance" if source == "binance" else "unified"
    row = service.submit_strategy(scope=scope, name="no RSI entry", rules=rules, source_kind="manual", source_reference="fixture")
    args = dict(scope=scope, strategy_key=row["strategy_key"], version_id=row["version_id"])
    service.strategy_action(**args, action="approve")
    result = service.run_strategy_historical_validation(**args, asset_class="stock" if stock else "crypto",
        source=source, symbol=symbol, limit=250,
        **({"range_start_ms":1700000000000+100*step, "range_end_ms":1700000000000+240*step, "holding_bars":20} if dated else {}))
    evidence = result["execution_validation"]
    assert evidence["metrics"]["decisions"] == 0
    assert evidence["metrics"]["assessment_status"] == "no_trades"
    assert evidence["guardrail_violations"] == 0
    assert evidence["passed"] is False
    if dated:
        assert evidence["metrics"]["assumptions"]["maximum_holding_bars"] == 20
        assert evidence["metrics"]["requested_range_start_ms"] == 1700000000000+100*step
    paper = service.strategy_action(**args, action="start_paper")
    assert paper["status"] == "paper_observing"
    assert paper["execution_validation"] == evidence
