import logging
import sqlite3
from datetime import datetime, timezone

from trading.leverage_policy import resolve_effective_leverage
from trading.execution_mode import ExecutionMode
from trading.recorder import Recorder
from trading.position_ownership import managed_trade_map
from trading.trader import Position, PositionSide
from trading.unified_trader import UnifiedTrader


def _position(*, owner="legacy_unknown", order_id=None):
    return Position(
        symbol="BTCUSDT",
        side=PositionSide.LONG,
        entry_price=100.0,
        current_price=101.0,
        quantity=1.0,
        leverage=1,
        unrealized_pnl=1.0,
        unrealized_pnl_percent=1.0,
        entry_time=datetime.now(timezone.utc),
        entry_order_id=order_id,
        position_owner=owner,
    )


def test_shared_leverage_policy_separates_configured_and_effective_values():
    normal = resolve_effective_leverage(
        configured_leverage=10, exchange="binance", market_level="NORMAL"
    )
    high = resolve_effective_leverage(
        configured_leverage=10, exchange="bybit", market_level="HIGH"
    )
    low = resolve_effective_leverage(
        configured_leverage=10, exchange="okx", market_level="LOW"
    )
    spot = resolve_effective_leverage(
        configured_leverage=10, exchange="bithumb", market_level="LOW"
    )

    assert (normal["configured"], normal["effective"]) == (10, 2)
    assert high["effective"] == 1
    assert low["effective"] == 3
    assert spot["effective"] == 1
    assert "레버리지를 사용하지 않음" in spot["reason"]


def test_cold_start_is_limited_not_permanently_blocked():
    result = resolve_effective_leverage(
        configured_leverage=10,
        exchange="bitget",
        market_level="LOW",
        cold_start_max_leverage=1,
    )
    assert result["effective"] == 1
    assert "신규/회복 제한운용" in result["reason"]


def test_recorder_returns_only_persisted_noah_owned_open_entries(tmp_path):
    db_path = tmp_path / "trading.db"
    recorder = Recorder(db_path=str(db_path), log_path=str(tmp_path / "logs"))
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO trade_log (
                symbol, side, entry_price, quantity, leverage, reason,
                entry_time, exchange, order_id, position_owner
            ) VALUES (?, 'LONG', 100, 1, 1, ?, ?, 'bithumb', ?, ?)
            """,
            [
                ("NOAH/KRW", "AI 거래 신호", now, "order-noah", "noahai"),
                ("MANUAL/KRW", "manual import", now, "order-manual", "legacy_unknown"),
            ],
        )

    rows = recorder.get_open_managed_trades("bithumb")
    assert [row["symbol"] for row in rows] == ["NOAH/KRW"]


def test_restart_recovery_aggregates_duplicate_noah_entries_for_same_symbol():
    rows = [
        {
            "symbol": "ZIL/KRW", "quantity": 2.0, "entry_price": 10.0,
            "order_id": "second", "entry_time": "2026-08-11T01:00:00+00:00",
            "spot_baseline_quantity": 1.0,
        },
        {
            "symbol": "KRW-ZIL", "quantity": 3.0, "entry_price": 20.0,
            "order_id": "first", "entry_time": "2026-08-11T00:00:00+00:00",
            "spot_baseline_quantity": 0.0,
        },
    ]

    recovered = managed_trade_map(rows)["ZILKRW"]

    assert recovered["quantity"] == 5.0
    assert recovered["entry_price"] == 16.0
    assert set(recovered["_entry_order_ids"]) == {"first", "second"}
    assert recovered["spot_baseline_quantity"] == 0.0


def test_unified_close_refuses_unowned_account_position():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = logging.getLogger("test.position.ownership")
    trader.get_exchange_client = lambda _exchange: (_ for _ in ()).throw(
        AssertionError("manual position must never reach an exchange order")
    )

    assert trader._close_position_unified(
        "binance", "BTCUSDT", _position(), 101.0
    ) is False


def test_spot_short_without_noah_long_protects_manual_balance():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = logging.getLogger("test.spot.short.manual")
    trader.settings = {}
    trader._execution_mode = lambda _exchange: ExecutionMode.LIVE
    trader._position_store = lambda _exchange: {}

    result = trader._execute_signal_trade(
        "upbit", "BTC/KRW", {"signal": "SHORT", "confidence": 0.9}
    )

    assert result["status"] == "skipped"
    assert "수동 보유자산을 보호" in result["reason"]


def test_spot_short_closes_only_owned_long_instead_of_opening_short():
    trader = UnifiedTrader.__new__(UnifiedTrader)
    trader.logger = logging.getLogger("test.spot.short.owned")
    trader.settings = {}
    trader._execution_mode = lambda _exchange: ExecutionMode.LIVE
    managed = _position(owner="noahai", order_id="owned-entry")
    managed.symbol = "BTC/KRW"
    trader._position_store = lambda _exchange: {"BTC/KRW": managed}
    trader.exchange_manager = type(
        "ExchangeManager", (), {"get_current_price": lambda self, *_args: 101.0}
    )()
    called = []
    trader._close_position_unified = lambda exchange, symbol, position, price: (
        called.append((exchange, symbol, position, price)) or True
    )

    result = trader._execute_signal_trade(
        "bithumb", "KRW-BTC", {"signal": "SHORT", "confidence": 0.9}
    )

    assert result["status"] == "success"
    assert len(called) == 1
    assert called[0][1] == "BTC/KRW"
