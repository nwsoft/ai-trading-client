from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from trading import notifications
from trading.notifications import NotificationDispatcher, NotificationMessage, _format_message
from trading.recorder import Recorder
from trading.risk_manager import RiskManager


VENUES = ("binance", "upbit", "bithumb", "bybit", "bitget", "okx")


class _NoDatabase:
    def get_daily_actual_trades(self, *_args, **_kwargs):
        return []


@pytest.mark.parametrize("venue", VENUES)
@pytest.mark.parametrize("mode", ("learning", "paper"))
def test_non_live_modes_never_read_account_or_emit_loss_alert(monkeypatch, venue, mode):
    manager = RiskManager(object(), _NoDatabase())
    account_reads = []
    events = []
    monkeypatch.setattr(
        manager,
        "_get_live_equity_snapshot",
        lambda source: account_reads.append(source) or pytest.fail("non-LIVE account read"),
    )
    monkeypatch.setattr(
        notifications,
        "publish_notification",
        lambda event_type, *_args, **_kwargs: events.append(event_type) or True,
    )

    decision = manager.evaluate_daily_loss_limit(venue, execution_mode=mode)

    assert decision.blocked is False
    assert decision.status == "not_applicable"
    assert decision.execution_mode == mode
    assert account_reads == []
    assert events == []


@pytest.mark.parametrize("venue", VENUES)
def test_invalid_live_balance_never_becomes_fake_100_percent_loss(monkeypatch, venue):
    manager = RiskManager(object(), _NoDatabase())
    events = []
    monkeypatch.setattr(manager, "_get_live_equity_snapshot", lambda _source: {
        "valid": False,
        "status": "empty_response",
        "reason": "valid account balance unavailable",
    })
    monkeypatch.setattr(
        notifications,
        "publish_notification",
        lambda event_type, title, message, **kwargs: events.append(
            (event_type, title, message, kwargs)
        ) or True,
    )

    decision = manager.evaluate_daily_loss_limit(venue, execution_mode="live")

    assert decision.blocked is True
    assert decision.status == "risk_data_unavailable"
    assert decision.loss_rate == 0.0
    assert events[0][0] == "risk_data_unavailable"
    assert events[0][3]["source"] == venue
    assert events[0][3]["execution_mode"] == "live"
    assert "100" not in events[0][2]
    assert all(event[0] != "guardrail_stop" for event in events)


def test_live_guardrail_uses_venue_pnl_not_raw_balance_change(monkeypatch):
    manager = RiskManager(object(), _NoDatabase())
    manager.daily_initial_balance = 100.0
    manager.max_daily_loss_percent = 10.0
    events = []
    # A withdrawal may reduce current equity, but without a NoahAI trading loss
    # it must not become a daily-loss event.
    monkeypatch.setattr(manager, "_get_live_equity_snapshot", lambda _source: {
        "valid": True, "equity": 20.0, "currency": "USDT",
    })
    monkeypatch.setattr(manager, "_today_live_trades", lambda _source: [])
    monkeypatch.setattr(manager, "_managed_unrealized_pnl", lambda _source, **kw: (True, 0.0, ""))
    monkeypatch.setattr(
        notifications,
        "publish_notification",
        lambda event_type, *_args, **_kwargs: events.append(event_type) or True,
    )

    decision = manager.evaluate_daily_loss_limit("bitget", execution_mode="live")

    assert decision.blocked is False
    assert decision.loss_rate == 0.0
    assert events == []


@pytest.mark.parametrize("venue", VENUES)
def test_real_live_loss_emits_mode_and_venue_specific_stop(monkeypatch, venue):
    manager = RiskManager(object(), _NoDatabase())
    manager.daily_initial_balance = 100.0
    manager.max_daily_loss_percent = 10.0
    events = []
    monkeypatch.setattr(manager, "_get_live_equity_snapshot", lambda _source: {
        "valid": True,
        "equity": 88.0,
        "currency": "KRW" if venue in {"upbit", "bithumb"} else "USDT",
    })
    monkeypatch.setattr(manager, "_today_live_trades", lambda _source: [{"net_pnl": -12.0, "performance_evidence_ready": True}])
    monkeypatch.setattr(manager, "_managed_unrealized_pnl", lambda _source, **kw: (True, 0.0, ""))
    monkeypatch.setattr(
        notifications,
        "publish_notification",
        lambda event_type, title, message, **kwargs: events.append(
            (event_type, title, message, kwargs)
        ) or True,
    )

    decision = manager.evaluate_daily_loss_limit(venue, execution_mode="live")

    assert decision.blocked is True
    assert decision.status == "loss_limit_exceeded"
    assert decision.loss_rate == pytest.approx(12.0)
    assert len(events) == 1
    assert events[0][0] == "guardrail_stop"
    assert events[0][3]["source"] == venue
    assert events[0][3]["execution_mode"] == "live"


def test_notification_venue_filter_and_mode_label(monkeypatch):
    dispatcher = NotificationDispatcher(max_queue=10)
    settings = {
        "notification_integrations": {
            "enabled": True,
            "channels": {
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE",
                },
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
            },
            "events": {"guardrail_stop": True},
            "exchanges": {"binance": True, "bitget": False},
            "cooldown_seconds": 0,
        }
    }
    # Keep this test deterministic; queue acceptance is the contract here.
    monkeypatch.setattr(dispatcher, "_deliver", lambda _item: None)
    dispatcher.configure(settings, scope="venue-filter")

    assert dispatcher.publish(NotificationMessage(
        "guardrail_stop", "stop", "loss", source="bitget", execution_mode="live"
    )) is False
    assert dispatcher.publish(NotificationMessage(
        "guardrail_stop", "stop", "loss", source="binance", execution_mode="live"
    )) is True
    text = _format_message(NotificationMessage(
        "guardrail_stop", "LIVE loss", "details", source="binance", execution_mode="live"
    ))
    assert text.startswith("[NoahAI][LIVE]")
    assert "BINANCE" in text
    dispatcher.shutdown(timeout=1.0)


def test_recorder_daily_trades_are_filtered_by_exchange_and_mode(tmp_path):
    recorder = Recorder(db_path=str(tmp_path / "trades.db"), log_path=str(tmp_path / "trades.log"))
    now = datetime.now().replace(microsecond=0).isoformat()
    with sqlite3.connect(recorder.db_path) as conn:
        for exchange, mode, pnl in (
            ("bitget", "live", -7.0),
            ("bitget", "paper", -90.0),
            ("bybit", "live", -80.0),
        ):
            conn.execute(
                """
                INSERT INTO trade_log (
                    symbol, side, entry_price, exit_price, quantity, leverage,
                    pnl, pnl_percent, reason, entry_time, exit_time, tp_price,
                    sl_price, fees, slippage, exchange, execution_mode
                ) VALUES (?, 'LONG', 100, 99, 1, 1, ?, -1, 'AI close', ?, ?, 101, 98, 0, 0, ?, ?)
                """,
                ("BTC/USDT:USDT", pnl, now, now, exchange, mode),
            )
        conn.commit()

    rows = recorder.get_daily_actual_trades(
        datetime.now(), exchange="bitget", execution_mode="live"
    )

    assert len(rows) == 1
    assert rows[0]["exchange"] == "bitget"
    assert rows[0]["execution_mode"] == "live"
    assert rows[0]["realized_pnl"] == pytest.approx(-7.0)
