from datetime import datetime, timedelta, timezone
import json
import sqlite3
import struct
from types import SimpleNamespace

import pytest

from web_platform.application_services import ApplicationServices
from web_platform.query_services import AccountQueryService
from web_platform.asset_insight_data import load_closed_trade_records, load_trade_history_metrics
from web_platform.interactive_ai import InteractiveAIService, InteractiveProviderFailure
from trading.ai.provider_router import NormalizedProviderError, ProviderResponse
from trading.exchanges.venue_capabilities import CRYPTO_VENUES, STOCK_VENUES
from trading.exchanges.adapters.kiwoom_host_launcher import pe_machine, start_32bit_host


@pytest.fixture
def paper_service(tmp_path):
    now = datetime.now(timezone.utc)
    rows = []
    for source in (*CRYPTO_VENUES, *STOCK_VENUES):
        currency = "KRW" if source in {*STOCK_VENUES, "upbit", "bithumb", "coinone"} else "USDT"
        for days, pnl in ((0, 3), (2, -1)):
            closed = now - timedelta(days=days, seconds=1)
            rows.append({"event_id": f"{source}-{days}", "exchange": source, "scope": "unified",
                         "symbol": "005930" if source in STOCK_VENUES else f"BTC/{currency}",
                         "execution_mode": "paper", "calculation_status": "valid", "net_pnl": pnl,
                         "fees": 0.1, "quote_currency": currency, "quantity": 1, "entry_price": 100,
                         "opened_at": (closed-timedelta(minutes=1)).isoformat(), "closed_at": closed.isoformat()})
    (tmp_path / "strategy_paper_outcomes.jsonl").write_text("\n".join(map(json.dumps, rows)))
    service = object.__new__(ApplicationServices)
    service.data_dir = tmp_path
    return service


@pytest.mark.parametrize("source", [*CRYPTO_VENUES, *STOCK_VENUES])
def test_paper_venue_and_all_dashboard_use_identical_currency_period_contract(paper_service, source):
    asset = "stock" if source in STOCK_VENUES else "crypto"
    # A fixed custom range avoids midnight-dependent tests.
    start = (datetime.now(timezone.utc)-timedelta(days=1)).isoformat()
    end = datetime.now(timezone.utc).isoformat()
    all_rows = paper_service._paper_statistics_snapshot(asset_class=asset, period="custom", custom_start=start, custom_end=end)
    selected = paper_service._paper_statistics_snapshot(asset_class=asset, source=source, period="custom", custom_start=start, custom_end=end)
    group = next(g for g in all_rows["groups"] if g["source"] == source)
    assert selected["closed_count"] == group["closed_count"] == 1
    assert selected["pnl_by_currency"] == {group["currency"]: group["total_pnl"]}
    assert selected["win_rate"] == 100
    lifetime = paper_service._paper_statistics_snapshot(asset_class=asset, source=source, period="all")
    assert lifetime["closed_count"] == 2
    assert sum(lifetime["pnl_by_currency"].values()) == 2


def test_analyst_paper_all_assets_and_persisted_answer(paper_service):
    summary = paper_service._paper_statistics_snapshot(asset_class="all", period="all")
    assert summary["closed_count"] == 2 * (len(CRYPTO_VENUES) + len(STOCK_VENUES))
    answer = ApplicationServices._assistant_operational_answer("현재 수익률 개선", {
        "execution": {"source": "binance", "execution_mode": "paper", "cycle_execution_metrics": []},
        "performance": paper_service._paper_statistics_snapshot(asset_class="crypto", source="binance", period="all"),
    })
    assert "2건" in answer and "+2.0000 USDT" in answer
    assert "메트릭이 없습니다" not in answer


@pytest.mark.parametrize("source,alias", [("kis", "koreaInvestment"), ("kiwoom", "kiwoom"), ("mirae", "miraeAsset"), ("shinhan", "shinhan")])
def test_stock_learning_filters_database_owner_before_pagination(tmp_path, source, alias):
    db = tmp_path / "trading.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE ai_decisions (id INTEGER PRIMARY KEY, symbol TEXT, created_at TEXT, decision_type TEXT, decision_json TEXT)")
        for index in range(35):
            c.execute("INSERT INTO ai_decisions VALUES (?, ?, ?, ?, ?)", (index, "005930", "2026-09-15 10:00:00", "stock_analyze_symbol", json.dumps({"broker": alias if index < 15 else "other", "confidence": .8, "signal": "LONG"})))
        c.execute("INSERT INTO ai_decisions VALUES (99, '005930', '', 'stock_analyze_symbol', 'invalid')")
    result = AccountQueryService(str(db)).learning_snapshot(source=source, limit=10)
    assert result["summary"]["total_count"] == 15
    assert result["summary"]["signal_counts"]["LONG"] == 15
    assert len(result["records"]) == 10 and result["pagination"]["has_more"]
    assert all(r["exchange"] == source for r in result["records"])
    assert "ai_decisions" in result["source"] and source in result["source"]
    second = AccountQueryService(str(db)).learning_snapshot(source=source, offset=10, limit=10)
    assert len(second["records"]) == 5 and not second["pagination"]["has_more"]


def test_unverified_and_paper_values_never_become_live_portfolio_performance(tmp_path):
    db = tmp_path / "trading.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE trade_log (symbol TEXT, exchange TEXT, pnl REAL, net_pnl REAL, entry_time TEXT, exit_time TEXT, execution_mode TEXT, reconciliation_status TEXT)")
        for mode, status, pnl, net in [("live", "exchange_confirmed", 10, 8), ("live", "legacy_unverified", -999, -999), ("paper", "exchange_confirmed", 200, 200)]:
            c.execute("INSERT INTO trade_log VALUES ('BTCUSDT','binance',?,?, '2026-09-01', '2026-09-02',?,?)", (pnl, net, mode, status))
    result = load_closed_trade_records(str(db), confirmed_only=True)
    assert [r["pnl"] for r in result["records"]] == [8]
    assert load_trade_history_metrics(str(db))["pnl_by_currency"] == {"USDT": 8}


def test_strategy_studio_question_routes_to_product_knowledge():
    service = object.__new__(ApplicationServices)
    answer = service._settings_support_answer("전략 스튜디오 백테스트 PnL MDD와 PAPER 차이", {})
    assert "PnL" in answer and "PAPER" in answer and "과거 재생" in answer
    selection = service._settings_support_answer("전략 스튜디오 일반과 고급의 코인 선정 및 국면 기준 차이", {"market_regime_check_interval_seconds": 600})
    assert "universe_policy" in selection and "regime_scope" in selection and "600초" in selection


def test_provider_failure_preserves_model_status_without_leaking_body(tmp_path):
    adapter = SimpleNamespace(model="test-model", is_ready=lambda: True,
        chat_text=lambda *args, **kwargs: ProviderResponse(provider="openai", model="test-model", error=NormalizedProviderError("openai", "rate_limit", "private-body", 429)))
    router = SimpleNamespace(spec=SimpleNamespace(provider="openai"), adapter=adapter)
    service = InteractiveAIService(data_dir=tmp_path, router_factory=lambda *args, **kwargs: router)
    with pytest.raises(InteractiveProviderFailure) as caught:
        service.ask(settings={}, workload="assistant", question="public test", context="", system_prompt="", max_tokens=200)
    assert caught.value.provider_called and caught.value.status_code == 429
    assert caught.value.model == "test-model" and "private-body" not in str(caught.value)


def test_kiwoom_host_missing_is_architecture_setup_error(tmp_path, monkeypatch):
    monkeypatch.setenv("NOAHAI_KIWOOM_HOST", str(tmp_path / "missing.exe"))
    with pytest.raises(RuntimeError, match="kiwoom_32bit_host_missing"):
        start_32bit_host({})


def test_kiwoom_pe_architecture_validation(tmp_path, monkeypatch):
    binary = bytearray(80)
    binary[:2] = b"MZ"
    struct.pack_into("<I", binary, 60, 64)
    binary[64:68] = b"PE\0\0"
    struct.pack_into("<H", binary, 68, 0x8664)
    path = tmp_path / "host.exe"
    path.write_bytes(binary)
    assert pe_machine(path) == 0x8664
    monkeypatch.setenv("NOAHAI_KIWOOM_HOST", str(path))
    with pytest.raises(RuntimeError, match="kiwoom_host_architecture_mismatch"):
        start_32bit_host({})
