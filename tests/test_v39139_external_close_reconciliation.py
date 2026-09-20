from __future__ import annotations

from datetime import datetime

import pytest

from trading.recorder import Recorder, TradeLog
from web_platform.query_services import AccountQueryService


def _recorder(tmp_path) -> Recorder:
    return Recorder(
        db_path=str(tmp_path / "trading.db"),
        log_path=str(tmp_path / "logs"),
        exchange="binance",
    )


def _closed_external_short(
    recorder: Recorder,
    *,
    entry_order_id: str,
    quantity: float,
    entry_time: datetime,
    exit_time: datetime,
) -> int:
    trade_id = recorder.insert_trade_log(TradeLog(
        id=None,
        symbol="AVAUSDT",
        entry_price=0.3198,
        exit_price=0.3034,
        quantity=quantity,
        leverage=1,
        pnl=0.0,
        pnl_percent=0.0,
        entry_time=entry_time,
        exit_time=exit_time,
        reason="TP/SL 청산",
        side="SHORT",
        tp_price=0.3034,
        sl_price=None,
        fees=0.0,
        # This fixture proves a fee-free entry; NULL is unknown, not zero.
        entry_fee=0.0,
        entry_fee_asset="USDT",
        slippage=0.0,
        exchange="binance",
        order_id=entry_order_id,
        exit_order_id=None,
        position_owner="noahai",
        execution_mode="live",
        settlement_currency="USDT",
        pnl_source="estimated_close_price",
        reconciliation_status="pending_exchange_reconciliation",
    ))
    assert trade_id is not None
    return trade_id


def _fill(*, fill_id: str, order_id: str, quantity: float, pnl: float, at: datetime, side="buy"):
    return {
        "id": fill_id,
        "order": order_id,
        "symbol": "AVAUSDT",
        "side": side,
        "price": 0.3034,
        "amount": quantity,
        "realized_pnl": pnl,
        "fee": {"cost": 0.0, "currency": "USDT"},
        "status": "closed",
        "timestamp": int(at.timestamp() * 1000),
    }


def test_single_external_close_requires_order_evidence_before_pnl_recovery(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_external_short(
        recorder,
        entry_order_id="entry-1",
        quantity=16.1,
        entry_time=datetime(2026, 9, 18, 0, 1, 27),
        exit_time=datetime(2026, 9, 18, 0, 3, 20),
    )

    recorder.save_exchange_execution_history("binance", [
        _fill(
            fill_id="fill-1",
            order_id="tp-close-1",
            quantity=16.1,
            pnl=0.25,
            at=datetime(2026, 9, 18, 0, 3, 13),
        ),
    ], source="binance_external_close_recovery")

    row = recorder.execute_query(
        "SELECT exit_order_id, gross_pnl, pnl, reconciliation_status "
        "FROM trade_log WHERE id = ?",
        (trade_id,),
    )[0]
    assert row == (None, None, 0.0, "candidate_requires_order_evidence")
    # Model an authoritative close-order response, not a time/quantity guess.
    recorder.execute_query("UPDATE trade_log SET exit_order_id=? WHERE id=?", ("tp-close-1", trade_id))
    recorder.reconcile_trade_log_with_executions("binance")
    assert recorder.execute_query("SELECT gross_pnl, net_pnl FROM trade_log WHERE id=?", (trade_id,))[0] == pytest.approx((0.25, 0.25))


def test_two_sequential_external_closes_preserve_both_realized_pnls(tmp_path):
    recorder = _recorder(tmp_path)
    first_id = _closed_external_short(
        recorder,
        entry_order_id="entry-1",
        quantity=16.1,
        entry_time=datetime(2026, 9, 18, 0, 1, 27),
        exit_time=datetime(2026, 9, 18, 0, 3, 20),
    )
    second_id = _closed_external_short(
        recorder,
        entry_order_id="entry-2",
        quantity=17.1,
        entry_time=datetime(2026, 9, 18, 0, 6, 13),
        exit_time=datetime(2026, 9, 18, 0, 27, 20),
    )

    recorder.save_exchange_execution_history("binance", [
        _fill(
            fill_id="fill-1",
            order_id="tp-close-1",
            quantity=16.1,
            pnl=0.25,
            at=datetime(2026, 9, 18, 0, 3, 13),
        ),
        _fill(
            fill_id="fill-2",
            order_id="tp-close-2",
            quantity=17.1,
            pnl=0.02,
            at=datetime(2026, 9, 18, 0, 27, 9),
        ),
    ], source="binance_external_close_recovery")

    assert recorder.execute_query("SELECT COUNT(*) FROM trade_log WHERE exit_order_id IS NOT NULL")[0][0] == 0
    for trade_id, order_id in ((first_id, "tp-close-1"), (second_id, "tp-close-2")):
        recorder.execute_query("UPDATE trade_log SET exit_order_id=? WHERE id=?", (order_id, trade_id))
    recorder.reconcile_trade_log_with_executions("binance")
    rows = recorder.execute_query(
        "SELECT id, exit_order_id, gross_pnl, reconciliation_status "
        "FROM trade_log ORDER BY id"
    )
    assert rows == [
        (first_id, "tp-close-1", 0.25, "exchange_confirmed"),
        (second_id, "tp-close-2", 0.02, "exchange_confirmed"),
    ]
    stats = AccountQueryService(str(tmp_path / "trading.db")).trading_statistics(
        asset_class="crypto",
        source="binance",
        period="all",
    )
    assert stats["closed_count"] == 2
    assert stats["reconciled_closed_count"] == 2
    assert stats["unresolved_closed_count"] == 0
    assert stats["pnl_by_currency"]["USDT"] == pytest.approx(0.27)


def test_ambiguous_external_close_remains_unresolved(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_external_short(
        recorder,
        entry_order_id="entry-ambiguous",
        quantity=16.1,
        entry_time=datetime(2026, 9, 18, 0, 1, 27),
        exit_time=datetime(2026, 9, 18, 0, 3, 20),
    )
    recorder.save_exchange_execution_history("binance", [
        _fill(
            fill_id="fill-a",
            order_id="candidate-a",
            quantity=16.1,
            pnl=0.25,
            at=datetime(2026, 9, 18, 0, 3, 12),
        ),
        _fill(
            fill_id="fill-b",
            order_id="candidate-b",
            quantity=16.1,
            pnl=0.24,
            at=datetime(2026, 9, 18, 0, 3, 13),
        ),
    ])

    row = recorder.execute_query(
        "SELECT exit_order_id, reconciliation_status FROM trade_log WHERE id = ?",
        (trade_id,),
    )[0]
    assert row == (None, "pending_exchange_reconciliation")


def test_old_same_side_fill_inside_long_position_is_not_used_as_exit(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_external_short(
        recorder,
        entry_order_id="entry-long-lived",
        quantity=16.1,
        entry_time=datetime(2026, 9, 18, 0, 1, 0),
        exit_time=datetime(2026, 9, 18, 0, 20, 20),
    )
    recorder.save_exchange_execution_history("binance", [
        _fill(
            fill_id="old-manual-buy",
            order_id="old-unrelated-order",
            quantity=16.1,
            pnl=0.01,
            at=datetime(2026, 9, 18, 0, 5, 0),
        ),
        _fill(
            fill_id="real-exit",
            order_id="tp-close-current",
            quantity=16.1,
            pnl=0.25,
            at=datetime(2026, 9, 18, 0, 20, 13),
        ),
    ])
    assert recorder.execute_query(
        "SELECT exit_order_id, gross_pnl FROM trade_log WHERE id = ?", (trade_id,),
    )[0] == (None, None)


def test_wrong_close_side_cannot_be_linked(tmp_path):
    recorder = _recorder(tmp_path)
    trade_id = _closed_external_short(
        recorder,
        entry_order_id="entry-wrong-side",
        quantity=16.1,
        entry_time=datetime(2026, 9, 18, 0, 1, 27),
        exit_time=datetime(2026, 9, 18, 0, 3, 20),
    )
    recorder.save_exchange_execution_history("binance", [
        _fill(
            fill_id="fill-sell",
            order_id="not-a-short-close",
            quantity=16.1,
            pnl=0.25,
            at=datetime(2026, 9, 18, 0, 3, 13),
            side="sell",
        ),
    ])
    assert recorder.execute_query(
        "SELECT exit_order_id FROM trade_log WHERE id = ?", (trade_id,),
    )[0][0] is None
