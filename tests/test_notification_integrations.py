from __future__ import annotations

import json
import threading
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from config.settings import _preserve_sensitive_values
from trading import notifications
from trading.risk_manager import RiskManager
from trading.notifications import (
    NotificationDeliveryError,
    NotificationDispatcher,
    NotificationMessage,
    discover_telegram_chats,
    notification_status,
    test_notification_channel as send_test_notification,
)
from web_platform.application_services import ApplicationServices
from web_platform.gateway import create_gateway_app


TOKEN = "test-gateway-token-that-is-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
CONFIRMED = {**AUTH, "X-NoahAI-Intent": "confirmed"}


def _settings() -> dict:
    return {
        "notification_integrations": {
            "enabled": True,
            "channels": {
                "discord": {
                    "enabled": True,
                    "webhook_url": "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE",
                },
                "telegram": {
                    "enabled": True,
                    "bot_token": "123456789:abcdefghijklmnopqrstuvwxyzABCDE",
                    "chat_id": "-1001234567890",
                },
            },
            "events": {"guardrail_stop": True, "report": True},
            "exchanges": {
                "binance": True, "upbit": True, "bithumb": True,
                "bybit": True, "bitget": True, "okx": True,
            },
            "cooldown_seconds": 300,
            "timeout_seconds": 5,
            "retry_count": 0,
        }
    }


def _write_path(target: dict, path: str, value) -> None:
    cursor = target
    parts = path.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = deepcopy(value)


class _Response:
    def __init__(self, payload: dict | None = None, *, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int) -> bytes:
        if self.payload is None:
            return b""
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def test_status_never_returns_notification_credentials():
    settings = _settings()

    result = notification_status(settings)

    serialized = json.dumps(result, ensure_ascii=False)
    assert result["channels"]["discord"] == {"enabled": True, "configured": True}
    assert result["channels"]["telegram"]["configured"] is True
    assert "discord.com/api/webhooks" not in serialized
    assert "123456789:abcdefghijklmnopqrstuvwxyzABCDE" not in serialized
    assert "-1001234567890" not in serialized


@pytest.mark.parametrize(
    "url",
    [
        "http://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE",
        "https://example.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE",
        "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE?redirect=https://example.com",
    ],
)
def test_discord_webhook_rejects_non_discord_and_unsafe_urls(url):
    settings = _settings()
    settings["notification_integrations"]["channels"]["discord"]["webhook_url"] = url

    with pytest.raises(NotificationDeliveryError, match="^discord_webhook_invalid$"):
        send_test_notification(settings, "discord")


def test_discord_test_posts_utf8_message_only_to_validated_webhook(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response({"id": "message-id"})

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)

    result = send_test_notification(_settings(), "discord")

    assert result["ok"] is True
    assert captured["url"].endswith("?wait=true")
    assert "연결 테스트 성공" in captured["body"]["content"]
    assert captured["timeout"] == 5


def test_telegram_discovery_returns_contacted_chats_without_token(monkeypatch):
    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/getMe"):
            return _Response({"ok": True, "result": {"username": "noah_test_bot", "first_name": "Noah"}})
        return _Response({
            "ok": True,
            "result": [
                {"message": {"chat": {"id": 777, "first_name": "사용자", "type": "private"}}},
                {"channel_post": {"chat": {"id": -100888, "title": "운영 알림", "type": "channel"}}},
            ],
        })

    monkeypatch.setattr(notifications, "urlopen", fake_urlopen)

    result = discover_telegram_chats(_settings())

    assert result["bot"]["username"] == "noah_test_bot"
    assert {row["chat_id"] for row in result["chats"]} == {"777", "-100888"}
    assert "123456789:abcdefghijklmnopqrstuvwxyzABCDE" not in json.dumps(result, ensure_ascii=False)


def test_dispatcher_is_nonblocking_deduplicated_and_stops_cleanly(monkeypatch):
    dispatcher = NotificationDispatcher(max_queue=10)
    delivered = []
    received = threading.Event()

    def fake_deliver(item, *, generation=None):
        delivered.append(item)
        received.set()

    monkeypatch.setattr(dispatcher, "_deliver", fake_deliver)
    dispatcher.configure(_settings())
    item = NotificationMessage("guardrail_stop", "거래 중단", "일일 손실 한도 도달", source="binance", dedupe_key="same")

    assert dispatcher.publish(item) is True
    assert dispatcher.publish(item) is False
    assert received.wait(1.0) is True
    assert delivered == [item]
    dispatcher.shutdown(timeout=1.0)


def test_dispatcher_drops_pending_message_after_account_generation_changes(monkeypatch):
    dispatcher = NotificationDispatcher(max_queue=10)
    delivered = []
    dispatcher._settings = deepcopy(_settings())
    dispatcher._generation = 4
    dispatcher._queue.put_nowait((4, NotificationMessage("report", "이전 계정", "보내면 안 됨")))
    dispatcher.configure({"notification_integrations": {"enabled": False}}, scope="next-account")
    dispatcher._queue.put_nowait(None)
    monkeypatch.setattr(notifications, "_deliver_discord", lambda *args: delivered.append(args))
    monkeypatch.setattr(notifications, "_deliver_telegram", lambda *args: delivered.append(args))

    dispatcher._run()

    assert delivered == []


def test_dispatcher_rejects_report_when_no_configured_channel_is_enabled():
    dispatcher = NotificationDispatcher(max_queue=10)
    settings = _settings()
    settings["notification_integrations"]["channels"]["discord"]["enabled"] = False
    settings["notification_integrations"]["channels"]["telegram"]["enabled"] = False
    dispatcher.configure(settings, scope="tester")

    assert dispatcher.publish(NotificationMessage("report", "리포트", "요약")) is False


@pytest.mark.parametrize(
    ("current_balance", "expected_stop", "expected_event"),
    [(89.0, True, "guardrail_stop"), (94.0, False, "loss_warning")],
)
def test_daily_loss_events_are_queued_without_changing_guardrail_result(
    monkeypatch, current_balance, expected_stop, expected_event,
):
    manager = RiskManager(
        object(),
        object(),
        settings={"notification_integrations": {"loss_warning_percent": 5}},
    )
    manager.daily_initial_balance = 100.0
    manager.max_daily_loss_percent = 10.0
    monkeypatch.setattr(manager, "_get_live_equity_snapshot", lambda _source: {
        "valid": True, "equity": current_balance, "currency": "KRW",
    })
    monkeypatch.setattr(
        manager,
        "_today_live_trades",
        lambda _source: [{"net_pnl": current_balance - 100.0, "performance_evidence_ready": True}],
    )
    monkeypatch.setattr(manager, "_managed_unrealized_pnl", lambda _source: (True, 0.0, ""))
    events = []
    monkeypatch.setattr(notifications, "publish_notification", lambda event_type, *_args, **kwargs: events.append((event_type, kwargs)) or True)

    result = manager.check_daily_loss_limit(source="upbit", execution_mode="live")

    assert result is expected_stop
    assert events[0][0] == expected_event
    assert events[0][1]["source"] == "upbit"


def test_reset_preserves_notification_credentials_but_uses_new_defaults():
    current = _settings()
    defaults = {
        "notification_integrations": {
            "enabled": False,
            "channels": {
                "discord": {"enabled": False, "webhook_url": ""},
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
            },
            "cooldown_seconds": 600,
        }
    }

    merged = _preserve_sensitive_values(current, defaults)

    assert merged["notification_integrations"]["channels"]["discord"]["webhook_url"].startswith("https://discord.com/")
    assert merged["notification_integrations"]["channels"]["telegram"]["bot_token"].startswith("123456789:")
    assert merged["notification_integrations"]["channels"]["telegram"]["chat_id"] == "-1001234567890"
    assert merged["notification_integrations"]["enabled"] is False
    assert merged["notification_integrations"]["cooldown_seconds"] == 600


def test_notification_credentials_save_reread_refresh_and_stay_write_only(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {
        "paper_trading": True,
        "notification_integrations": {
            "enabled": False,
            "channels": {
                "discord": {"enabled": False, "webhook_url": ""},
                "telegram": {"enabled": False, "bot_token": "", "chat_id": ""},
            },
            "events": {"guardrail_stop": True},
        },
    }
    configured = []

    class _Bridge:
        def refresh_settings(self, settings):
            self.settings = deepcopy(settings)

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda _account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **_kwargs: deepcopy(stored))

    def patch_paths(changes):
        for path, value in changes.items():
            _write_path(stored, path, value)
        return True

    monkeypatch.setattr(service_module, "patch_settings_paths", patch_paths)
    monkeypatch.setattr(notifications, "configure_notifications", lambda settings, **_kwargs: configured.append(deepcopy(settings)))
    services = ApplicationServices(account="tester", runtime_bridge=_Bridge())
    before = services.settings_snapshot()

    after = services.update_credentials(
        expected_revision=before["revision"],
        provider="notification:discord",
        values={"webhook_url": "https://discord.com/api/webhooks/1234567890/abcdefghijklmnopqrstuvwxyzABCDE"},
    )

    serialized = json.dumps(after, ensure_ascii=False)
    assert after["save_receipt"]["verified"] is True
    assert after["credential_status"]["notification:discord"] is True
    assert stored["notification_integrations"]["channels"]["discord"]["webhook_url"].startswith("https://discord.com/")
    assert "abcdefghijklmnopqrstuvwxyzABCDE" not in serialized
    assert configured[-1]["notification_integrations"]["channels"]["discord"]["webhook_url"].endswith("abcdefghijklmnopqrstuvwxyzABCDE")


class _NotificationServices:
    def runtime_snapshot(self):
        return {"status": "detached", "reason": "test"}

    def notification_status(self):
        return {"enabled": True, "channels": {"discord": {"configured": True}}}

    def test_notification(self, *, channel):
        return {"ok": True, "channel": channel}

    def discover_telegram_chats(self):
        return {"ok": True, "chats": []}

    def send_report_notification(self, *, title, message, source=""):
        return {"ok": True, "queued": True, "title": title, "source": source}


def test_notification_gateway_requires_token_and_confirmed_user_intent():
    client = TestClient(create_gateway_app(token=TOKEN, application_services=_NotificationServices()))

    assert client.get("/api/v1/notifications/status").status_code == 401
    assert client.get("/api/v1/notifications/status", headers=AUTH).status_code == 200
    assert client.post("/api/v1/notifications/test", headers=AUTH, json={"channel": "discord"}).status_code == 428
    response = client.post("/api/v1/notifications/test", headers=CONFIRMED, json={"channel": "discord"})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "channel": "discord"}
