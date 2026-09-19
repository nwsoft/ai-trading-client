from types import SimpleNamespace
import json
import pytest

from trading.strategy_scope import scope_matches, scoped_pool
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.selection_policy import _scope_matches
from web_platform.advanced_services import AdvancedFeatureServices
from web_platform.query_services import AccountQueryService
from web_platform.application_services import ApplicationServices


@pytest.mark.parametrize("venue", ["binance", "upbit", "bithumb", "coinone", "bybit", "okx", "bitget"])
def test_crypto_scope_is_not_stock(venue):
    for match in (scope_matches, _scope_matches, DeclarativeStrategyEngine._scope_matches):
        assert match("exchange:" + venue, asset_class="crypto", target=venue)
        assert not match("exchange:" + venue, asset_class="stock", target=venue)
        assert not match("asset:stock", asset_class="crypto", target=venue)


@pytest.mark.parametrize("venue,alias", [("kis", "koreaInvestment"), ("mirae", "miraeAsset"), ("kiwoom", "kiwoom"), ("shinhan", "shinhan")])
@pytest.mark.parametrize("asset", ["stock", "etf"])
def test_stock_etf_and_alias_contract(venue, alias, asset):
    for match in (scope_matches, _scope_matches, DeclarativeStrategyEngine._scope_matches):
        assert match("broker:" + venue, asset_class=asset, target=alias)
        assert match("asset:stock", asset_class=asset, target=alias)
        assert not match("asset:crypto", asset_class=asset, target=alias)


def test_subset_never_broadens_and_cap_follows_scope():
    assert scope_matches("exchange:binance,bybit", asset_class="crypto", target="bybit")
    assert not scope_matches("exchange:binance,bybit", asset_class="crypto", target="okx")
    assert not scope_matches("exchange:", asset_class="crypto", target="binance")
    rows = [{"target_scope": "asset:crypto", "priority": 10} for _ in range(20)]
    stock = {"target_scope": "broker:kis,kiwoom", "priority": 1}
    assert scoped_pool(rows + [stock], asset_class="etf", target="koreaInvestment") == [stock]


def test_cash_and_paper_performance_are_separate(tmp_path):
    service = AdvancedFeatureServices(data_dir=tmp_path, queries=AccountQueryService(db_path=str(tmp_path / "missing.db")))
    result = service.portfolio_analysis(account_snapshot={"sources": {
        "kis": {"status": "success", "balance": {"cash": 10000, "stock_eval": 5000},
                "positions": [{"symbol": "005930", "quantity": 1, "current_price": 5000}]},
        "binance": {"status": "success", "balance": {"balance": {"USDT": {"total": 20}}}, "positions": []},
        "kiwoom": {"status": "connection_failed", "balance": {"cash": 999}, "positions": []},
    }}, paper_records=[{"pnl": 300, "currency": "KRW"}])
    assert result["allocation_by_currency"]["KRW"]["total_value"] == 15000
    assert result["allocation_by_currency"]["USDT"]["total_value"] == 20
    assert result["performance_by_currency"]["KRW"]["net_pnl"] == 300
    assert result["execution_mode"] == "paper"


def test_scenario_paper_excludes_live(tmp_path):
    queries = AccountQueryService(db_path=str(tmp_path / "missing.db"))
    result = queries.scenario_snapshot(paper_records=[{"asset_class": "stock", "currency": "KRW", "pnl": 10}])
    assert result["execution_mode"] == "paper"
    assert result["scopes"]["stock"]["sample_count"] == 1
    assert result["scopes"]["crypto"]["sample_count"] == 0
    assert result["scopes"]["stock"]["scenarios"][1]["total_pnl"] == 10
    assert queries.scenario_snapshot()["scopes"]["stock"]["sample_count"] == 0


def test_venue_compatibility_uses_declared_scope_not_storage_owner():
    result = ApplicationServices._strategy_venue_compatibility(scope="binance", rules={"target_scope": "exchange:bybit,okx"})
    assert {row["venue"] for row in result} == {"bybit", "okx"}
    result = ApplicationServices._strategy_venue_compatibility(scope="unified", rules={"target_scope": "broker:kis,kiwoom"})
    assert {row["venue"] for row in result} == {"kis", "kiwoom"}


def test_host_constructor_failure_has_typed_ready_failure(monkeypatch):
    import trading.exchanges.adapters.kiwoom_stock_adapter as adapter
    from trading.exchanges.adapters.kiwoom_process_proxy import _kiwoom_process_main
    def fail(**kwargs):
        raise ValueError("private credential must not appear")
    monkeypatch.setattr(adapter, "KiwoomStockAdapter", fail)
    sent = []
    connection = SimpleNamespace(send=sent.append, close=lambda: None)
    with pytest.raises(ValueError):
        _kiwoom_process_main(connection, {}, ready_handshake=True)
    assert sent == [(0, False, "kiwoom_host_initialization_failed:ValueError")]


def test_host_diagnostics_do_not_store_config(tmp_path, monkeypatch):
    from trading.exchanges.adapters.kiwoom_host_diagnostics import record_stage
    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("NOAHAI_KIWOOM_DIAGNOSTIC_LOG", str(path))
    record_stage("adapter_ready")
    event = json.loads(path.read_text())
    assert set(event) == {"at", "pid", "stage", "error_type"}


def test_single_venue_refresh_preserves_other_venues():
    import threading
    service = object.__new__(ApplicationServices)
    service._account_state_lock = threading.Lock()
    service._account_refresh_cache = {}
    service._account_refresh_events = {}
    service._latest_account_snapshot = None
    service._audit = lambda *args, **kwargs: None
    service.runtime_bridge = SimpleNamespace(account_snapshot=lambda sources, force_refresh: {
        "sources": {source: {"status": "success", "balance": {"cash": 10}} for source in sources},
    })
    service.refresh_account_snapshot(sources=["kis"])
    service.refresh_account_snapshot(sources=["binance"])
    assert set(service._latest_account_snapshot["sources"]) == {"kis", "binance"}
    assert service._latest_account_snapshot["sources"]["kis"]["captured_at"]


def test_futures_notional_is_not_added_to_wallet_balance():
    rows = AdvancedFeatureServices._position_rows({"sources": {"binance": {
        "status": "success", "balance": {"balance": {"USDT": 100}},
        "positions": [{"symbol": "BTCUSDT", "quantity": 1, "mark_price": 100000}],
    }}})
    assert sum(row.get("allocation_value", row["market_value"]) for row in rows) == 100
    assert rows[-1]["market_value"] == 100000  # exposure is retained, not fabricated equity


def test_scenario_currency_filter_keeps_mixed_ledgers_separate(tmp_path):
    query = AccountQueryService(db_path=str(tmp_path / "missing.db"))
    rows = [{"asset_class": "crypto", "currency": "KRW", "pnl": 100},
            {"asset_class": "crypto", "currency": "USDT", "pnl": 2}]
    result = query.scenario_snapshot(paper_records=rows, currency="USDT")
    assert result["available_currencies"] == ["KRW", "USDT"]
    assert result["scopes"]["crypto"]["sample_count"] == 1
    assert result["scopes"]["crypto"]["scenarios"][1]["total_pnl"] == 2
