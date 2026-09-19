from __future__ import annotations

import json

import pytest

from trading.paper_strategy_ledger import (
    paper_quote_currency,
    read_paper_strategy_outcomes,
)
from trading.stock_analysis_service import StockAnalysisService
from trading.stock_paper_valuation import (
    DEFAULT_STOCK_PAPER_COSTS,
    normalize_stock_paper_cost_policy,
)
from web_platform.application_services import ApplicationServices


BROKERS = ("kiwoom", "shinhan", "miraeAsset", "koreaInvestment")


class _NoTradeHistoryAdapter:
    api_type = "rest"
    exchange_name = "test"

    def get_today_trades(self):
        raise AssertionError("PAPER must not read LIVE broker trades")

    def get_trade_history(self, limit=50):
        raise AssertionError("PAPER must not read LIVE broker trades")


@pytest.mark.parametrize("broker", BROKERS)
@pytest.mark.parametrize("asset_class,tax_rate", [("stock", 0.002), ("etf", 0.0)])
def test_four_brokers_stock_and_etf_active_paper_pnl_is_net_and_krw(
    broker, asset_class, tax_rate,
):
    service = StockAnalysisService(_NoTradeHistoryAdapter(), broker_name=broker)
    service._paper_positions_by_broker.pop(broker.lower(), None)
    symbol = "005930" if asset_class == "stock" else "069500"

    success, _, errors = service._place_paper_stock_order(
        symbol=symbol,
        side="BUY",
        quantity=10,
        price=100,
        order_type="MARKET",
        asset_class=asset_class,
    )
    assert success is True and errors == []
    valuation = service._refresh_paper_position_valuation(symbol, 101)
    position = service._paper_positions()[symbol]

    expected_fees = 1000 * 0.00015 + 1010 * 0.00015
    expected_slippage = 1000 * 0.0003 + 1010 * 0.0003
    expected_tax = 1010 * tax_rate
    expected_net = 10.0 - expected_fees - expected_slippage - expected_tax
    assert valuation["net_pnl"] == pytest.approx(expected_net)
    assert position["unrealized_pnl"] == pytest.approx(expected_net)
    assert position["estimated_fees"] == pytest.approx(expected_fees)
    assert position["estimated_taxes"] == pytest.approx(expected_tax)
    assert position["estimated_slippage"] == pytest.approx(expected_slippage)
    assert position["quote_currency"] == "KRW"
    assert position["side"] == "LONG"


@pytest.mark.parametrize("broker", BROKERS)
@pytest.mark.parametrize("asset_class,expected_tax", [("stock", 2.02), ("etf", 0.0)])
def test_stock_paper_close_records_complete_cost_contract(
    tmp_path, monkeypatch, broker, asset_class, expected_tax,
):
    import trading.paper_strategy_ledger as ledger

    monkeypatch.setattr(ledger, "get_app_data_dir", lambda: str(tmp_path))
    service = StockAnalysisService(_NoTradeHistoryAdapter(), broker_name=broker)
    service._paper_positions_by_broker.pop(broker.lower(), None)
    symbol = "005930" if asset_class == "stock" else "069500"
    service._place_paper_stock_order(
        symbol=symbol, side="BUY", quantity=10, price=100,
        order_type="MARKET", asset_class=asset_class,
    )
    before = dict(service._paper_positions()[symbol])
    success, result, errors = service._place_paper_stock_order(
        symbol=symbol, side="SELL", quantity=10, price=101,
        order_type="MARKET", asset_class=asset_class,
    )
    assert success is True and errors == []
    assert result["gross_pnl"] == pytest.approx(10.0)
    assert result["estimated_taxes"] == pytest.approx(expected_tax)
    assert result["net_pnl"] == pytest.approx(10.0 - result["total_cost"])
    assert result["quote_currency"] == "KRW"

    service._record_stock_paper_outcome(
        position_before=before,
        order_result=result,
        strategy_key="stock-strategy",
        version_id="v1",
    )
    rows = read_paper_strategy_outcomes()
    assert len(rows) == 1
    row = rows[0]
    assert row["exchange"] == broker.lower()
    assert row["quote_currency"] == "KRW"
    assert row["side"] == "LONG"
    assert row["entry_price"] == pytest.approx(100)
    assert row["exit_price"] == pytest.approx(101)
    assert row["quantity"] == pytest.approx(10)
    assert row["gross_pnl"] == pytest.approx(10)
    assert row["net_pnl"] == pytest.approx(result["net_pnl"])
    assert row["fees"] == pytest.approx(result["fees"])
    assert row["estimated_taxes"] == pytest.approx(expected_tax)
    assert row["estimated_slippage"] == pytest.approx(result["estimated_slippage"])
    assert row["cost_calculation_status"] == "estimated_stock_paper_contract"


def test_stock_paper_never_sells_more_than_owned_position():
    service = StockAnalysisService(_NoTradeHistoryAdapter(), broker_name="kiwoom")
    service._paper_positions_by_broker.pop("kiwoom", None)
    service._place_paper_stock_order(
        symbol="005930", side="BUY", quantity=2, price=100,
        order_type="MARKET",
    )
    success, _, errors = service._place_paper_stock_order(
        symbol="005930", side="SELL", quantity=3, price=101,
        order_type="MARKET",
    )
    assert success is False
    assert errors == ["paper_sell_quantity_exceeds_position"]
    assert service._paper_positions()["005930"]["quantity"] == 2


def test_stock_paper_partial_close_allocates_entry_cost_once():
    service = StockAnalysisService(_NoTradeHistoryAdapter(), broker_name="kiwoom")
    service._paper_positions_by_broker.pop("kiwoom", None)
    service._place_paper_stock_order(
        symbol="005930", side="BUY", quantity=10, price=100,
        order_type="MARKET", asset_class="stock",
    )
    original = dict(service._paper_positions()["005930"])

    success, first_close, errors = service._place_paper_stock_order(
        symbol="005930", side="SELL", quantity=4, price=101,
        order_type="MARKET", asset_class="stock",
    )
    assert success is True and errors == []
    remaining = service._paper_positions()["005930"]
    assert first_close["quantity"] == pytest.approx(4)
    assert remaining["quantity"] == pytest.approx(6)
    assert remaining["entry_fees"] == pytest.approx(original["entry_fees"] * 0.6)
    assert remaining["entry_slippage"] == pytest.approx(original["entry_slippage"] * 0.6)

    success, second_close, errors = service._place_paper_stock_order(
        symbol="005930", side="SELL", quantity=6, price=102,
        order_type="MARKET", asset_class="stock",
    )
    assert success is True and errors == []
    assert "005930" not in service._paper_positions()
    assert first_close["fees"] + second_close["fees"] == pytest.approx(
        original["entry_fees"]
        + (4 * 101 + 6 * 102) * DEFAULT_STOCK_PAPER_COSTS["sell_commission_rate"]
    )


def test_stock_paper_profitability_samples_are_paper_only(monkeypatch):
    import trading.paper_strategy_ledger as ledger

    monkeypatch.setattr(ledger, "read_paper_strategy_outcomes", lambda: [
        {
            "event_id": "other", "exchange": "shinhan", "symbol": "005930",
            "closed_at": "2026-09-04T00:00:00+00:00", "net_pnl": 999,
            "calculation_status": "valid",
        },
        {
            "event_id": "old", "exchange": "kiwoom", "symbol": "005930",
            "closed_at": "2026-09-04T00:00:00+00:00", "net_pnl": -2,
            "calculation_status": "valid",
        },
        {
            "event_id": "new", "exchange": "kiwoom", "symbol": "069500",
            "closed_at": "2026-09-04T01:00:00+00:00", "net_pnl": 3,
            "calculation_status": "valid",
        },
    ])
    service = StockAnalysisService(_NoTradeHistoryAdapter(), broker_name="kiwoom")
    rows = service._get_recent_paper_trade_samples(limit=1)
    assert [row["event_id"] for row in rows] == ["new"]
    assert rows[0]["pnl_is_net"] is True


def test_stock_paper_cycle_never_reads_live_broker_trade_history(monkeypatch):
    class Recorder:
        exchange = ""

        def save_ai_decision(self, *args, **kwargs):
            return None

    service = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name="kiwoom", recorder=Recorder(),
    )
    monkeypatch.setattr(service, "get_market_regime", lambda: "range")
    monkeypatch.setattr(service, "_sync_runtime_state_snapshot", lambda: {})
    monkeypatch.setattr(service, "_get_recent_trade_samples", lambda **_kwargs: (_ for _ in ()).throw(
        AssertionError("PAPER selected LIVE sample path")
    ))
    monkeypatch.setattr(service, "_get_recent_paper_trade_samples", lambda **_kwargs: [])
    monkeypatch.setattr(service, "analyze_symbol", lambda symbol: {
        "status": "ok", "symbol": symbol, "current_price": 100.0,
        "score": 50.0, "momentum": 0.0, "is_etf": False,
        "analysis_type": "stock", "score_model": "test", "reasoning": "test",
    })

    result = service.run_auto_trade_cycle(
        symbols=["005930"],
        execution_mode_override="paper",
        auto_risk_policy={"profitability_validation": {"enabled": False}},
        exit_policy={"enable_exit_policy": False},
    )
    assert result["execution_mode"] == "paper"
    assert result["orders_executed"] == 0


def test_stock_xai_log_receives_explicit_broker_owner():
    class Recorder:
        def __init__(self):
            self.calls = []

        def save_ai_decision(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    recorder = Recorder()
    service = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name="koreaInvestment", recorder=recorder,
    )
    service._persist_xai_decision("005930", "stock_auto_trade_symbol", {"action": "HOLD"})
    assert recorder.calls[0][1]["exchange"] == "koreaInvestment"


def test_stock_evidence_total_cost_includes_tax_and_is_krw():
    evidence = ApplicationServices._strategy_paper_evidence_by_venue([{
        "exchange": "kiwoom", "symbol": "005930", "net_pnl": 7.0,
        "fees": 0.3, "estimated_taxes": 2.0, "estimated_slippage": 0.6,
        "calculation_status": "valid",
        "cost_calculation_status": "estimated_stock_paper_contract",
    }])[0]
    assert evidence["quote_currency"] == "KRW"
    assert evidence["estimated_taxes"] == pytest.approx(2.0)
    assert evidence["total_cost"] == pytest.approx(2.9)
    assert evidence["estimated_cost_trades"] == 1
    assert evidence["recovered_cost_trades"] == 0


def test_stock_cost_policy_fallback_is_visible_in_evidence():
    evidence = ApplicationServices._strategy_paper_evidence_by_venue([{
        "exchange": "kiwoom", "symbol": "005930", "net_pnl": 1.0,
        "calculation_status": "valid",
        "cost_calculation_status": "estimated_stock_paper_contract_with_fallback",
        "cost_policy_issues": ["stock_sell_tax_rate:outside_fraction_range"],
    }])[0]
    assert evidence["cost_policy_issue_trades"] == 1
    assert evidence["recovered_cost_trades"] == 0


@pytest.mark.parametrize("broker", BROKERS)
def test_stock_broker_currency_fallback_is_krw(broker):
    assert paper_quote_currency(broker, "005930") == "KRW"


def test_invalid_percent_unit_does_not_become_thirty_percent_cost():
    policy = normalize_stock_paper_cost_policy({
        "paper_costs": {"stock_sell_tax_rate": 30},
    })
    assert policy["stock_sell_tax_rate"] == DEFAULT_STOCK_PAPER_COSTS["stock_sell_tax_rate"]
    assert policy["cost_source"] == "invalid_settings_fallback"
    assert policy["cost_calculation_status"] == "estimated_stock_paper_contract_with_fallback"
    assert policy["cost_policy_issues"] == ["stock_sell_tax_rate:outside_fraction_range"]


def test_normalized_stock_cost_policy_keeps_custom_rates_on_second_pass():
    first = normalize_stock_paper_cost_policy({
        "paper_costs": {"stock_sell_tax_rate": 0.0015},
    })
    second = normalize_stock_paper_cost_policy(first)
    assert second["stock_sell_tax_rate"] == pytest.approx(0.0015)
    assert second["cost_source"] == "settings.paper_costs"
    assert second["cost_policy_issues"] == []


def test_settings_template_exposes_stock_paper_cost_contract():
    with open("config/settings_template.json", encoding="utf-8") as handle:
        settings = json.load(handle)
    costs = settings["stock_auto_trading"]["paper_costs"]
    assert costs["stock_sell_tax_rate"] == pytest.approx(0.002)
    assert costs["etf_sell_tax_rate"] == pytest.approx(0.0)


@pytest.mark.parametrize("broker", BROKERS)
def test_stock_paper_open_position_survives_restart_with_strategy_identity(
    tmp_path, broker,
):
    settings = {"paper_position_store_path_stock": str(tmp_path / "stock-paper.json")}
    broker_key = broker.lower()
    StockAnalysisService._paper_positions_by_broker.clear()
    first = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name=broker, paper_settings=settings,
    )
    success, _, errors = first._place_paper_stock_order(
        symbol="005930", side="BUY", quantity=2, price=70_000,
        order_type="MARKET", asset_class="stock",
    )
    assert success is True and errors == []
    first._paper_positions()["005930"].update({
        "custom_strategy_key": "stock-strategy",
        "custom_strategy_version_id": "version-7",
        "custom_strategy_name": "restart-safe",
    })
    first._persist_paper_positions()

    StockAnalysisService._paper_positions_by_broker.clear()
    restored = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name=broker, paper_settings=settings,
    )
    position = restored._paper_positions_by_broker[broker_key]["005930"]
    assert position["execution_mode"] == "paper"
    assert position["quote_currency"] == "KRW"
    assert position["quantity"] == pytest.approx(2)
    assert position["custom_strategy_key"] == "stock-strategy"
    assert position["custom_strategy_version_id"] == "version-7"


def test_stock_paper_restore_rejects_non_paper_or_malformed_rows(tmp_path):
    path = tmp_path / "stock-paper.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "execution_mode": "paper",
        "asset_scope": "domestic_stock_etf",
        "brokers": {"kiwoom": {
            "005930": {"symbol": "005930", "side": "LONG", "quantity": 1,
                       "entry_price": 70_000, "quote_currency": "KRW",
                       "execution_mode": "live"},
            "000660": {"symbol": "000660", "side": "LONG", "quantity": 0,
                       "entry_price": 100_000, "quote_currency": "KRW",
                       "execution_mode": "paper"},
        }},
    }), encoding="utf-8")
    StockAnalysisService._paper_positions_by_broker.clear()
    service = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name="kiwoom",
        paper_settings={"paper_position_store_path_stock": str(path)},
    )
    assert service._paper_positions() == {}


def test_stock_paper_account_switch_does_not_reuse_previous_account_memory(tmp_path):
    first_settings = {
        "paper_position_store_path_stock": str(tmp_path / "account-a.json"),
    }
    second_settings = {
        "paper_position_store_path_stock": str(tmp_path / "account-b.json"),
    }
    StockAnalysisService._paper_positions_by_broker.clear()
    first = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name="kiwoom",
        paper_settings=first_settings,
    )
    first._place_paper_stock_order(
        symbol="005930", side="BUY", quantity=1, price=70_000,
        order_type="MARKET", asset_class="stock",
    )
    first._persist_paper_positions()
    assert "005930" in first._paper_positions()

    second = StockAnalysisService(
        _NoTradeHistoryAdapter(), broker_name="kiwoom",
        paper_settings=second_settings,
    )
    assert second._paper_positions() == {}
