from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta

import pytest

from web_platform.application_services import ApplicationServices
from web_platform.query_services import AccountQueryService


def _create_trade_db(path):
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trade_log (
                id INTEGER PRIMARY KEY, symbol TEXT, exchange TEXT, asset_type TEXT,
                side TEXT, entry_price REAL, exit_price REAL, quantity REAL,
                pnl REAL, pnl_percent REAL, fees REAL, entry_time TEXT, exit_time TEXT,
                reason TEXT, order_id TEXT, execution_mode TEXT
            );
            CREATE TABLE exchange_trade_stats (
                exchange TEXT, total_trades INTEGER, winning_trades INTEGER, total_pnl REAL
            );
            CREATE TABLE exchange_execution_log (
                id INTEGER PRIMARY KEY, exchange TEXT, cost REAL,
                confirmation_status TEXT, created_at TEXT, executed_at TEXT
            );
            """
        )


def test_display_statistics_ignore_mixed_unit_summary_cache(tmp_path):
    db_path = tmp_path / "trading.db"
    _create_trade_db(db_path)
    now = datetime.now().astimezone().isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO trade_log VALUES (1, 'BTCUSDT', 'binance', 'crypto', 'LONG', "
            "100, 101, 1, 8, 8, 2, ?, ?, 'take_profit', 'o1', 'live')",
            (now, now),
        )
        # Historical unified writers could put percent values in this column.
        connection.execute("INSERT INTO exchange_trade_stats VALUES ('binance', 999, 999, 123456)")

    service = AccountQueryService(str(db_path))
    overview = service.trading_overview(asset_class="crypto", period="all")
    statistics = service.trading_statistics(asset_class="crypto", period="all")

    assert overview["closed_count"] == 1
    assert overview["pnl_by_currency"] == {"USDT": 0.0}
    assert overview["unresolved_closed_count"] == 1
    assert statistics["closed_count"] == 1
    assert statistics["pnl_by_currency"] == {}
    assert statistics["unresolved_closed_count"] == 1
    assert statistics["ledger_authority"] == "trade_log"


def test_live_statistics_exclude_paper_learning_and_map_legacy_binance_aliases(tmp_path):
    db_path = tmp_path / "trading.db"
    _create_trade_db(db_path)
    now = datetime.now().astimezone().isoformat()
    rows = [
        (1, "live", 1.0),
        (2, "optimized", 2.0),
        (3, "manual", 3.0),
        (4, "paper", 100.0),
        (5, "learning", 100.0),
    ]
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, 'BTCUSDT', 'binance', 'crypto', 'LONG', "
            "100, 101, 1, ?, 1, 0, ?, ?, 'close', 'order', ?)",
            [(row_id, pnl, now, now, mode) for row_id, mode, pnl in rows],
        )

    statistics = AccountQueryService(str(db_path)).trading_statistics(
        asset_class="crypto", source="binance", period="all",
    )

    assert statistics["closed_count"] == 3
    # v3.9.1.28 keeps the legacy execution-mode mapping for the trade count,
    # but does not present un-reconciled legacy PnL as exact money statistics.
    assert statistics["pnl_by_currency"] == {}
    assert statistics["unresolved_closed_count"] == 3


def test_period_filters_and_non_destructive_baseline(tmp_path):
    db_path = tmp_path / "trading.db"
    _create_trade_db(db_path)
    now = datetime.now().astimezone()
    old = (now - timedelta(days=10)).isoformat()
    current = now.isoformat()
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO trade_log VALUES (?, '005930', 'kiwoom', 'stock', 'LONG', "
            "100, 101, 1, ?, 1, 0, ?, ?, 'close', 'order', 'live')",
            [(1, 5.0, old, old), (2, 7.0, current, current)],
        )

    query = AccountQueryService(str(db_path))
    assert query.trading_statistics(asset_class="stock", period="7d")["closed_count"] == 1
    assert query.trading_statistics(asset_class="stock", period="30d")["closed_count"] == 2
    after_now = (now + timedelta(seconds=1)).isoformat()
    hidden = query.trading_statistics(
        asset_class="stock", period="all", baseline_at=after_now,
    )
    assert hidden["closed_count"] == 0
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM trade_log").fetchone()[0] == 2


def test_all_six_exchanges_and_four_brokers_use_the_same_scoped_live_contract(tmp_path):
    db_path = tmp_path / "trading.db"
    _create_trade_db(db_path)
    now = datetime.now().astimezone().isoformat()
    crypto = [
        ("BTCUSDT", "binance"), ("KRW-BTC", "upbit"), ("BTC/KRW", "bithumb"),
        ("BTC/USDT:USDT", "bybit"), ("BTC/USDT:USDT", "bitget"), ("BTC/USDT:USDT", "okx"),
    ]
    stocks = [
        ("005930", "kiwoom"), ("005930", "shinhan"),
        ("005930", "miraeAsset"), ("005930", "koreaInvestment"),
    ]
    rows = []
    for row_id, (symbol, venue) in enumerate(crypto + stocks, start=1):
        asset = "crypto" if row_id <= len(crypto) else "stock"
        rows.append((row_id, symbol, venue, asset, now, now))
    with sqlite3.connect(db_path) as connection:
        connection.executemany(
            "INSERT INTO trade_log (id, symbol, exchange, asset_type, side, entry_price, exit_price, "
            "quantity, pnl, pnl_percent, fees, entry_time, exit_time, reason, order_id, execution_mode) "
            "VALUES (?, ?, ?, ?, 'LONG', 100, 101, 1, 1, 1, 0.1, ?, ?, 'close', 'order', 'live')",
            rows,
        )

    query = AccountQueryService(str(db_path))
    assert query.trading_statistics(asset_class="crypto", period="all")["closed_count"] == 6
    assert query.trading_statistics(asset_class="stock", period="all")["closed_count"] == 4
    for venue in ("binance", "upbit", "bithumb", "bybit", "bitget", "okx"):
        assert query.trading_statistics(asset_class="crypto", source=venue, period="all")["closed_count"] == 1
    for broker in ("kiwoom", "shinhan", "mirae", "kis"):
        assert query.trading_statistics(asset_class="stock", source=broker, period="all")["closed_count"] == 1


def test_statistics_baseline_store_sets_and_clears_without_touching_ledgers(tmp_path):
    service = ApplicationServices.__new__(ApplicationServices)
    service._lock = threading.RLock()
    service.statistics_view_path = tmp_path / "statistics_view_state.json"
    service._audit = lambda *_args, **_kwargs: None

    state = service.update_statistics_view_baseline(
        service="blockchain", source="binance", action="set",
    )
    assert state["active"] is True
    assert state["records_deleted"] is False
    assert state["learning_preserved"] is True

    restored = service.update_statistics_view_baseline(
        service="blockchain", source="binance", action="clear",
    )
    assert restored["active"] is False


def test_all_venue_baseline_can_be_restored_for_one_venue_only(tmp_path):
    service = ApplicationServices.__new__(ApplicationServices)
    service._lock = threading.RLock()
    service.statistics_view_path = tmp_path / "statistics_view_state.json"
    service._audit = lambda *_args, **_kwargs: None

    service.update_statistics_view_baseline(service="blockchain", source="", action="set")
    assert service.statistics_view_state(service="blockchain", source="binance")["active"] is True
    assert service.statistics_view_state(service="blockchain", source="upbit")["active"] is True

    restored = service.update_statistics_view_baseline(
        service="blockchain", source="binance", action="clear",
    )

    assert restored["active"] is False
    assert service.statistics_view_state(service="blockchain", source="upbit")["active"] is True

    service.update_statistics_view_baseline(service="blockchain", source="", action="set")
    assert service.statistics_view_state(service="blockchain", source="binance")["active"] is True


@pytest.mark.parametrize(
    ("service_name", "source"),
    [
        ("blockchain", "binance"), ("blockchain", "upbit"),
        ("blockchain", "bithumb"), ("blockchain", "bybit"),
        ("blockchain", "bitget"), ("blockchain", "okx"),
        ("stock", "kiwoom"), ("stock", "shinhan"),
        ("stock", "miraeAsset"), ("stock", "koreaInvestment"),
    ],
)
def test_each_supported_institution_has_an_isolated_non_destructive_baseline(tmp_path, service_name, source):
    service = ApplicationServices.__new__(ApplicationServices)
    service._lock = threading.RLock()
    service.statistics_view_path = tmp_path / "statistics_view_state.json"
    service._audit = lambda *_args, **_kwargs: None

    state = service.update_statistics_view_baseline(
        service=service_name, source=source, action="set",
    )

    assert state["active"] is True
    assert state["records_deleted"] is False
    assert state["learning_preserved"] is True
    assert state["paper_preserved"] is True
    assert state["risk_ledgers_preserved"] is True
    other_service = "stock" if service_name == "blockchain" else "blockchain"
    assert service.statistics_view_state(service=other_service, source="")["active"] is False


def test_web_ui_keeps_period_and_reset_controls_in_statistics_tab_only():
    statistics_ui = open("webui/src/components/TradingStatisticsWorkspace.tsx", encoding="utf-8").read()
    source_ui = open("webui/src/components/LegacyFeatureWorkspaces.tsx", encoding="utf-8").read()
    operations_ui = open("webui/src/components/Operations.tsx", encoding="utf-8").read()

    for label in ("오늘", "7일", "30일", "전체", "사용자 지정", "통계 표시 기준 새로 시작"):
        assert label in statistics_ui
    assert "통계 표시 기준 새로 시작" not in source_ui
    assert "운영 KPI · 오늘" in operations_ui
    assert "현재 계좌 + 오늘 LIVE 청산" in operations_ui
