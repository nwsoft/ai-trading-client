import hashlib
import sqlite3

import pytest

from web_platform.asset_insight_data import load_live_history_evidence
from web_platform.advanced_services import AdvancedFeatureServices
from web_platform.query_services import AccountQueryService


@pytest.fixture
def ledger(tmp_path):
    path = tmp_path / "trading.db"
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE trade_log (symbol TEXT, exchange TEXT, entry_time TEXT,
            exit_time TEXT, pnl REAL, execution_mode TEXT, reconciliation_status TEXT,
            net_pnl REAL, position_owner TEXT, reason TEXT, settlement_currency TEXT)""")
        rows = [
            ("BTC/USDT", "binance", 10, "live", "legacy_unverified", None, "noahai", "", None),
            ("ETH/USDT", "binance", 20, "optimized", "legacy_unverified", None, "noahai", "", None),
            ("BTC/USDT", "binance", 10, "live", "legacy_unverified", None, "legacy_unknown", "binance_import", None),
            ("005930", "koreaInvestment", 100, "live", "legacy_unverified", None, "noahai", "", None),
            ("AAPL", "kis", 5, "live", "legacy_unverified", None, "noahai", "", None),
            ("MSFT", "kis", 6, "live", "legacy_unverified", None, "noahai", "", "USD"),
            ("BTC/USDT", "binance", 99, "live", "exchange_confirmed", 90, "noahai", "", "USDT"),
            ("BTC/USDT", "binance", 80, "live", "exchange_confirmed", 75, "external", "", "USDT"),
            ("BTC/USDT", "binance", None, "live", "exchange_confirmed", None, "noahai", "", None),
            ("BTC/USDT", "binance", 99999, "paper", "exchange_confirmed", 99999, "noahai", "", "USDT"),
            ("BTC/USDT", "binance", 99999, "learning", "legacy_unverified", None, "noahai", "", None),
        ]
        for index, row in enumerate(rows):
            db.execute("INSERT INTO trade_log VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                       (*row[:2], "2025-01-01", f"2025-01-{index+1:02d}", *row[2:]))
    return path


def test_history_inventory_readonly_full_counts_and_separate_buckets(ledger):
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    result = load_live_history_evidence(ledger, limit=2)
    assert result["total_count"] == 9
    assert result["confirmed_count"] == 1
    assert result["reference_count"] == 8
    assert len(result["recent_records"]) == 2
    groups = {(r["category"], r["currency"]): r for r in result["groups"]}
    assert groups["unreconciled", "USDT"]["stored_pnl_sum"] == 30
    assert groups["unreconciled", "USDT"]["missing_pnl_count"] == 1
    assert groups["imported", "USDT"]["stored_pnl_sum"] == 10
    assert groups["external", "USDT"]["count"] == 1
    assert set(result["available_currencies"]) == {"KRW", "USDT", "UNKNOWN", "USD"}
    assert result["first_exit_time"] == "2025-01-01"
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before


def test_scope_currency_and_missing_are_not_zero(ledger):
    result = load_live_history_evidence(ledger, asset_class="stock", currency="KRW")
    assert result["total_count"] == 1
    assert result["recent_records"][0]["symbol"] == "005930"
    assert result["available_currencies"] == ["KRW", "UNKNOWN", "USD"]
    result = load_live_history_evidence(ledger, asset_class="crypto", currency="USDT")
    assert result["recent_records"][0]["stored_pnl"] is None


def test_services_preserve_confirmed_and_paper_performance(ledger, tmp_path):
    queries = AccountQueryService(db_path=str(ledger))
    service = AdvancedFeatureServices(data_dir=tmp_path, queries=queries)
    result = service.portfolio_analysis(account_snapshot=None)
    assert result["live_history_evidence"]["reference_count"] == 8
    assert result["performance_by_currency"]["USDT"]["net_pnl"] == 90
    assert result["allocation_by_currency"] == {}
    paper = [{"pnl": 7, "currency": "KRW", "asset_class": "stock"}]
    assert service.portfolio_analysis(account_snapshot=None, paper_records=paper)["performance_by_currency"]["KRW"]["net_pnl"] == 7
    scenario = queries.scenario_snapshot(currency="USDT")
    assert scenario["scopes"]["all"]["sample_count"] == 1
    assert scenario["scopes"]["all"]["scenarios"][1]["total_pnl"] == 90
    assert scenario["scopes"]["stock"]["sample_count"] == 0
    assert scenario["scopes"]["crypto"]["live_history_evidence"]["reference_count"] == 5
    scenario = queries.scenario_snapshot(paper_records=paper)
    assert scenario["scopes"]["stock"]["scenarios"][1]["total_pnl"] == 7


def test_legacy_schema_and_read_error(tmp_path):
    path = tmp_path / "old.db"
    assert load_live_history_evidence(path)["status"] == "unavailable"
    assert not path.exists()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE trade_log (symbol TEXT, pnl REAL, exit_time TEXT)")
        db.execute("INSERT INTO trade_log VALUES ('BTC/USDT', 12, '2020-01-01')")
    result = load_live_history_evidence(path)
    assert result["reference_count"] == 1
    assert result["confirmed_count"] == 0
    assert result["recent_records"][0]["stored_pnl"] == 12
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM trade_log")
    assert load_live_history_evidence(path)["status"] == "available"
    assert load_live_history_evidence(path)["total_count"] == 0


@pytest.mark.parametrize("pnl", [float("inf"), float("-inf"), "bad"])
def test_nonfinite_stored_pnl_is_missing(tmp_path, pnl):
    path = tmp_path / "invalid.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE trade_log (symbol TEXT, pnl REAL, exit_time TEXT)")
        db.execute("INSERT INTO trade_log VALUES ('BTC/USDT', ?, '2020-01-01')", (pnl,))
    result = load_live_history_evidence(path)
    assert result["groups"][0]["stored_pnl_sum"] is None
    assert result["recent_records"][0]["stored_pnl"] is None
