from datetime import datetime, timezone
from unittest.mock import MagicMock

from trading import stock_analysis_service as sas


def make_service(recorder):
    adapter = MagicMock()
    adapter.broker_name = "kis"
    return sas.StockAnalysisService(adapter, broker_name="kis", recorder=recorder)


def test_stock_buy_is_saved_as_open_position(monkeypatch):
    recorder = MagicMock()
    recorder.insert_trade_log.return_value = 41
    service = make_service(recorder)
    opened_payload = {}

    def fake_opened(**kwargs):
        opened_payload.update(kwargs)
        return True, kwargs["position_id"]

    monkeypatch.setattr(sas, "emit_position_opened", fake_opened)

    result = service._insert_auto_trade_log(
        symbol="005930",
        side="BUY",
        quantity=3,
        price=70000,
        score=80,
        momentum=1.0,
        order_result={"order_id": "BUY-1", "filled_price": 70100},
    )

    saved = recorder.insert_trade_log.call_args.args[0]
    assert saved.exit_time is None
    assert saved.entry_time.tzinfo == timezone.utc
    assert saved.entry_price == 70100
    assert result["event"] == "opened"
    assert opened_payload["entry_order_id"] == "BUY-1"


def test_stock_sell_closes_fifo_lot_and_emits_holdable_event(monkeypatch):
    recorder = MagicMock()
    opened_at = datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc)
    recorder.execute_query.side_effect = [
        [(41, 70000.0, 3.0, opened_at.isoformat(), "BUY-1", 100.0)],
        [],
    ]
    service = make_service(recorder)
    closed_payload = {}

    def fake_closed(**kwargs):
        closed_payload.update(kwargs)
        return True

    monkeypatch.setattr(sas, "emit_position_closed", fake_closed)

    result = service._insert_auto_trade_log(
        symbol="005930",
        side="SELL",
        quantity=3,
        price=74000,
        score=20,
        momentum=-1.0,
        order_result={"order_id": "SELL-1", "filled_price": 74200},
        close_reason="take_profit",
    )

    assert result["unmatched_quantity"] == 0
    assert result["events"][0]["event"] == "closed"
    assert closed_payload["opened_at"] == opened_at
    assert closed_payload["entry_price"] == 70000.0
    assert closed_payload["exit_price"] == 74200
    assert closed_payload["closed_quantity"] == 3.0
    assert closed_payload["gross_pnl"] == 12600.0
    assert closed_payload["exit_order_id"] == "SELL-1"


def test_stock_partial_sell_preserves_remaining_open_lot(monkeypatch):
    recorder = MagicMock()
    opened_at = datetime(2026, 7, 24, 1, 0, tzinfo=timezone.utc)
    recorder.execute_query.side_effect = [
        [(41, 70000.0, 5.0, opened_at.isoformat(), "BUY-1", 100.0)],
        [],
    ]
    recorder.insert_trade_log.return_value = 42
    service = make_service(recorder)
    reduced_payload = {}

    def fake_reduced(**kwargs):
        reduced_payload.update(kwargs)
        return True

    monkeypatch.setattr(sas, "emit_position_reduced", fake_reduced)

    result = service._insert_auto_trade_log(
        symbol="005930",
        side="SELL",
        quantity=2,
        price=72000,
        score=30,
        momentum=-0.5,
        order_result={"order_id": "SELL-2", "filled_price": 72000},
    )

    update_query, update_params = recorder.execute_query.call_args_list[1].args
    closed_lot = recorder.insert_trade_log.call_args.args[0]
    assert "SET quantity = ?, fees = ?" in update_query
    assert update_params == (3.0, 60.0, 41)
    assert closed_lot.quantity == 2.0
    assert closed_lot.exit_time is not None
    assert result["events"][0]["event"] == "reduced"
    assert reduced_payload["remaining_quantity"] == 3.0
