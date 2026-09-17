"""Isolated account-ledger coverage; no exchange or broker network requests."""
import hashlib
import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from trading.exchanges.venue_capabilities import CRYPTO_VENUE_ORDER, STOCK_VENUE_ORDER
from web_platform.source_trade_history import load_source_live_history
from web_platform.query_services import AccountQueryService

VENUES = [*CRYPTO_VENUE_ORDER, *STOCK_VENUE_ORDER]


def make_db(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE trade_log (
            id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, asset_type TEXT,
            entry_time TEXT, exit_time TEXT, pnl REAL, net_pnl REAL,
            reconciliation_status TEXT, execution_mode TEXT, position_owner TEXT,
            reason TEXT, settlement_currency TEXT, side TEXT, entry_price REAL,
            exit_price REAL, quantity REAL, strategy_key TEXT, version_id TEXT)""")


def insert(path, venue, **changes):
    stock = venue in STOCK_VENUE_ORDER
    row = dict(symbol="005930" if stock else "BTCUSDT", exchange=venue,
               asset_type="stock" if stock else "crypto", entry_time="2026-09-16 09:00:00",
               exit_time="2026-09-17 13:00:00", pnl=123456, net_pnl=1200 if stock else 1.25,
               reconciliation_status="broker_order_linked" if stock else "exchange_confirmed",
               execution_mode="live", position_owner="noahai", reason="close",
               settlement_currency="KRW" if stock or venue in {"upbit", "bithumb", "coinone"} else "USDT",
               side="LONG", entry_price=70000 if stock else 60000,
               exit_price=71200 if stock else 61000, quantity=1,
               strategy_key="trend_follow", version_id="v-test")
    row.update(changes)
    with sqlite3.connect(path) as db:
        db.execute(f"INSERT INTO trade_log ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))


@pytest.mark.parametrize("venue", VENUES)
def test_all_venues_scoped_readonly_history_and_workspace(tmp_path, venue):
    path = tmp_path / "account.db"
    make_db(path)
    insert(path, venue)
    insert(path, venue, execution_mode="paper", symbol="PAPER_LEAK")
    insert(path, venue, execution_mode="learning", symbol="LEARNING_LEAK")
    insert(path, venue, exit_time=None, symbol="OPEN_NOT_CLOSED")
    insert(path, venue, exit_time="", symbol="BLANK_NOT_CLOSED")
    insert(path, "bybit" if venue != "bybit" else "kis", symbol="OTHER_VENUE")
    insert(path, venue, net_pnl=None, symbol="UNCONFIRMED")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = load_source_live_history(path, source=venue)
    assert result["status"] == "available"
    assert len(result["records"]) == 2
    assert {r["source"] for r in result["records"]} == {venue}
    confirmed = next(r for r in result["records"] if r["evidence"] == "confirmed")
    unconfirmed = next(r for r in result["records"] if r["evidence"] == "unreconciled")
    assert confirmed["net_pnl"] != 123456  # never use the legacy raw pnl as net
    assert confirmed["strategy_key"] == "trend_follow" and confirmed["version_id"] == "v-test"
    assert unconfirmed["net_pnl"] is None and unconfirmed["evidence"] == "unreconciled"
    service = "stock" if venue in STOCK_VENUE_ORDER else "blockchain"
    payload = AccountQueryService(str(path)).workspace(service, f"{service}.source_workspaces", source=venue)
    assert payload["live_history"] == result
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("venue", STOCK_VENUE_ORDER)
@pytest.mark.parametrize("symbol,asset", [("005930", "stock"), ("069500", "etf")])
def test_stock_and_etf_rows_not_dropped(tmp_path, venue, symbol, asset):
    path = tmp_path / "account.db"
    make_db(path)
    insert(path, venue, symbol=symbol, asset_type=asset)
    row = load_source_live_history(path, source=venue)["records"][0]
    assert (row["symbol"], row["asset_type"], row["currency"], row["net_pnl"]) == (symbol, asset, "KRW", 1200)


@pytest.mark.parametrize("alias,canonical", [("koreaInvestment", "kis"), ("korea_investment", "kis"), ("mirae_asset", "mirae"), ("miraeasset", "mirae"), ("BINANCE", "binance")])
def test_aliases_filtered_before_limit(tmp_path, alias, canonical):
    path = tmp_path / "account.db"
    make_db(path)
    insert(path, canonical, exchange=alias)
    for i in range(55):
        insert(path, "okx", exit_time=f"2027-01-01 {i:03d}")
    result = load_source_live_history(path, source=canonical, limit=1)
    assert len(result["records"]) == 1 and result["records"][0]["source"] == canonical
    assert not result["has_more"]


@pytest.mark.parametrize("changes,evidence", [
    ({"net_pnl": float("inf")}, "unreconciled"),
    ({"net_pnl": "bad"}, "unreconciled"),
    ({"execution_mode": None}, "unreconciled"),
    ({"reconciliation_status": "pending"}, "unreconciled"),
    ({"position_owner": "external"}, "external"),
    ({"position_owner": "manual"}, "external"),
    ({"reason": "binance_import"}, "imported"),
])
def test_unverified_not_zero_or_confirmed(tmp_path, changes, evidence):
    path = tmp_path / "account.db"
    make_db(path)
    insert(path, "binance", **changes)
    row = load_source_live_history(path, source="binance")["records"][0]
    assert row["net_pnl"] is None and row["evidence"] == evidence


def test_empty_failure_missing_scope_and_old_schema_are_distinct(tmp_path):
    path = tmp_path / "missing.db"
    assert load_source_live_history(path, source="binance")["status"] == "unavailable"
    assert not path.exists()
    make_db(path)
    assert load_source_live_history(path, source="binance")["status"] == "available"
    assert load_source_live_history(path, source="")["error"] == "source_required"
    with sqlite3.connect(path) as db:
        db.execute("DROP TABLE trade_log")
        db.execute("CREATE TABLE trade_log (symbol TEXT, exit_time TEXT)")
        db.execute("INSERT INTO trade_log VALUES ('UNKNOWN_VENUE', '2026-09-17')")
    result = load_source_live_history(path, source="binance")
    assert result["status"] == "unavailable" and not result["records"]


def test_limit_and_currency_and_zero(tmp_path):
    path = tmp_path / "account.db"
    make_db(path)
    insert(path, "kis", symbol="AAPL", settlement_currency=None, net_pnl=0)
    row = load_source_live_history(path, source="kis")["records"][0]
    assert row["currency"] == "UNKNOWN" and row["net_pnl"] is None
    for i in range(51):
        insert(path, "binance", net_pnl=0, exit_time=f"2026-09-17 {i:03d}")
    result = load_source_live_history(path, source="binance")
    assert len(result["records"]) == 50 and result["has_more"]
    assert result["records"][0]["exit_time"].endswith("050")
    assert result["records"][0]["net_pnl"] == 0


def test_account_isolation_and_mixed_timestamp_sort(tmp_path):
    one, two = tmp_path / "one.db", tmp_path / "two.db"
    for path in (one, two):
        make_db(path)
    insert(one, "binance", symbol="OLDER", exit_time="2026-09-17T00:00:00+09:00")
    insert(one, "binance", symbol="NEWEST", exit_time="2026-09-17 01:00:00+00:00")
    insert(two, "binance", symbol="OTHER_ACCOUNT")
    assert load_source_live_history(one, source="binance", limit=1)["records"][0]["symbol"] == "NEWEST"
    assert load_source_live_history(two, source="binance")["records"][0]["symbol"] == "OTHER_ACCOUNT"


def browser_fixtures():
    with tempfile.TemporaryDirectory(prefix="noah-source-history-") as directory:
        path = Path(directory) / "isolated.db"
        make_db(path)
        for venue in VENUES:
            insert(path, venue)
            if venue in STOCK_VENUE_ORDER:
                insert(path, venue, symbol="069500", asset_type="etf")
            insert(path, venue, symbol="UNCONFIRMED", net_pnl=None)
            insert(path, venue, symbol="PAPER_MUST_NOT_LEAK", execution_mode="paper")
        return {venue: load_source_live_history(path, source=venue) for venue in VENUES}


@pytest.mark.parametrize("venue", VENUES)
def test_real_recorder_schema_roundtrip(tmp_path, venue):
    from datetime import datetime, timezone
    from trading.recorder import Recorder, TradeLog
    path = tmp_path / "real-recorder.db"
    recorder = Recorder(db_path=str(path), log_path=str(tmp_path / "logs"), exchange=venue)
    stock = venue in STOCK_VENUE_ORDER
    trade = TradeLog(id=None, symbol="069500" if stock else "BTCUSDT", entry_price=100,
        exit_price=105, quantity=1, leverage=1, pnl=4, pnl_percent=4,
        entry_time=datetime.now(timezone.utc), exit_time=datetime.now(timezone.utc),
        reason="qa", side="LONG", tp_price=None, sl_price=None, fees=1, slippage=0,
        exchange=venue, position_owner="noahai", execution_mode="live", net_pnl=4,
        settlement_currency="KRW" if stock else "USDT",
        reconciliation_status="broker_order_linked" if stock else "exchange_confirmed")
    assert recorder.insert_trade_log(trade)
    row = load_source_live_history(path, source=venue)["records"][0]
    assert row["symbol"] == trade.symbol and row["net_pnl"] == 4
    assert row["evidence"] == "confirmed"
    # Current Recorder has no strategy identity columns: never invent attribution.
    assert row["strategy_key"] == "" and row["version_id"] == ""


if __name__ == "__main__":
    print(json.dumps(browser_fixtures()))
