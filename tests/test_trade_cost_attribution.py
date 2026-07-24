import sqlite3
from datetime import datetime

from trading.recorder import Recorder, TradeLog


def test_trade_log_tracks_fill_model_variant_and_actual_fee(tmp_path):
    db_path = tmp_path / "trading.db"
    recorder = Recorder(db_path=str(db_path), log_path=str(tmp_path / "logs"))
    trade_id = recorder.insert_trade_log(
        TradeLog(
            id=None,
            symbol="BTCUSDT",
            entry_price=100.0,
            exit_price=None,
            quantity=1.0,
            leverage=1,
            pnl=None,
            pnl_percent=None,
            entry_time=datetime(2026, 7, 24, 10, 0, 0),
            exit_time=None,
            reason="test",
            side="BUY",
            tp_price=101.0,
            sl_price=99.0,
            fees=0.02,
            slippage=0.0,
            exchange="binance",
            order_id="entry-1",
            model_version="gpt-test",
            strategy_variant="ai_event_driven",
            fee_asset="USDT",
            fee_source="exchange_fill",
        )
    )
    assert trade_id

    assert recorder.update_trade_log(
        symbol="BTCUSDT",
        exit_price=101.0,
        exit_time=datetime(2026, 7, 24, 11, 0, 0),
        pnl_percent=1.0,
        pnl_usdt=1.0,
        exit_reason="TP",
        additional_fees=0.03,
        exit_order_id="exit-1",
        fee_asset="USDT",
        fee_source="exchange_fill",
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT order_id, exit_order_id, model_version, strategy_variant,
                   fees, fee_asset, fee_source
            FROM trade_log WHERE id = ?
            """,
            (trade_id,),
        ).fetchone()

    assert row == (
        "entry-1",
        "exit-1",
        "gpt-test",
        "ai_event_driven",
        0.05,
        "USDT",
        "exchange_fill",
    )
