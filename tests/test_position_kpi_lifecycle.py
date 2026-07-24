from datetime import datetime, timedelta, timezone

from api import position_kpi


def test_naive_local_datetime_is_normalized_to_aware_utc():
    normalized = position_kpi.as_utc(datetime(2026, 7, 24, 12, 0, 0))

    assert normalized is not None
    assert normalized.tzinfo == timezone.utc


def test_elapsed_seconds_does_not_hide_invalid_time_as_zero():
    opened_at = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
    closed_at = opened_at - timedelta(seconds=1)

    assert position_kpi.elapsed_seconds(opened_at, closed_at) is None


def test_closed_event_uses_same_utc_timestamps_and_elapsed_seconds(monkeypatch):
    captured = {}

    def fake_emit(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(position_kpi, "emit_kpi_event", fake_emit)
    opened_at = datetime(2026, 7, 24, 3, 0, tzinfo=timezone.utc)
    closed_at = opened_at + timedelta(minutes=95)

    emitted = position_kpi.emit_position_closed(
        asset_class="crypto",
        venue="binance",
        symbol="BTCUSDT",
        side="LONG",
        opened_at=opened_at,
        closed_at=closed_at,
        entry_price=100.0,
        exit_price=110.0,
        closed_quantity=1.0,
        close_reason="take_profit",
        entry_order_id="entry-1",
        exit_order_id="exit-1",
    )

    metadata = captured["metadata"]
    assert emitted is True
    assert captured["event_type"] == "trade_position_closed"
    assert metadata["hold_seconds"] == 5700.0
    assert metadata["opened_at"] == opened_at.isoformat()
    assert metadata["closed_at"] == closed_at.isoformat()
    assert metadata["event_id"].endswith(":closed:exit-1")


def test_opened_event_rejects_missing_execution_price(monkeypatch):
    called = False

    def fake_emit(**kwargs):
        nonlocal called
        called = True
        return True

    monkeypatch.setattr(position_kpi, "emit_kpi_event", fake_emit)

    emitted, position_id = position_kpi.emit_position_opened(
        asset_class="stock",
        venue="kis",
        symbol="005930",
        side="LONG",
        opened_at=position_kpi.utc_now(),
        entry_price=0.0,
        quantity=1.0,
    )

    assert emitted is False
    assert position_id is not None
    assert called is False
