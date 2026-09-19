#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Non-blocking, account-local outbound notifications for NoahAI.

Trading code only calls :func:`publish_notification`.  Network delivery lives
on one bounded worker queue so a slow or unavailable messenger can never hold
an exchange loop, settings lock, or risk guardrail.
"""

from __future__ import annotations

import json
import logging
import math
import queue
import re
import threading
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from trading.exchanges.venue_capabilities import SUPPORTED_VENUES, normalize_venue


LOGGER = logging.getLogger(__name__)
DISCORD_HOSTS = {"discord.com", "www.discord.com", "discordapp.com", "www.discordapp.com"}
DISCORD_PATH = re.compile(r"^/api(?:/v\d+)?/webhooks/\d+/[A-Za-z0-9._-]{20,}/?$")
TELEGRAM_TOKEN = re.compile(r"^\d{5,20}:[A-Za-z0-9_-]{20,}$")
TELEGRAM_CHAT_ID = re.compile(r"^-?\d{1,20}$")
SUPPORTED_CHANNELS = {"discord", "telegram"}
SUPPORTED_EVENTS = {
    "guardrail_stop",
    "loss_warning",
    "risk_data_unavailable",
    "market_regime_change",
    "runtime_failure",
    "update_available",
    "report",
    "test",
}


class NotificationDeliveryError(RuntimeError):
    """Safe error with a code suitable for UI and logs."""


@dataclass(frozen=True)
class NotificationMessage:
    event_type: str
    title: str
    message: str
    source: str = ""
    execution_mode: str = ""
    severity: str = "info"
    dedupe_key: str = ""
    occurred_at: str = ""


def _configuration(settings: dict[str, Any] | None) -> dict[str, Any]:
    raw = (settings or {}).get("notification_integrations")
    return deepcopy(raw) if isinstance(raw, dict) else {}


def _bounded_int(value: Any, default: int, maximum: int) -> int:
    try:
        return max(0, min(int(default if value is None else value), maximum))
    except (TypeError, ValueError, OverflowError):
        return default


def _channel_config(settings: dict[str, Any] | None, channel: str) -> dict[str, Any]:
    config = _configuration(settings)
    channels = config.get("channels")
    if not isinstance(channels, dict):
        return {}
    value = channels.get(channel)
    return deepcopy(value) if isinstance(value, dict) else {}


def _event_enabled(config: dict[str, Any], event_type: str) -> bool:
    if event_type in {"test", "report"}:
        return True
    events = config.get("events")
    return bool(events.get(event_type, False)) if isinstance(events, dict) else False


def _source_enabled(config: dict[str, Any], source: str) -> bool:
    """Return whether a venue may emit outbound notifications.

    The setting is opt-out for backward compatibility: accounts saved before
    v3.9.1.17 have no ``exchanges`` map and must keep receiving their valid
    LIVE alerts until the user changes the new per-venue switches.
    """
    venue = normalize_venue(source)
    if not venue:
        return True
    exchanges = config.get("exchanges")
    if not isinstance(exchanges, dict):
        return True
    # Legacy broker aliases and public IDs must describe the same switch.
    # If conflicting aliases exist, an explicit opt-out wins.
    matches = [bool(value) for key, value in exchanges.items() if normalize_venue(key) == venue]
    return all(matches) if matches else True


def _channel_ready(settings: dict[str, Any] | None, channel: str) -> bool:
    config = _channel_config(settings, channel)
    if not bool(config.get("enabled", False)):
        return False
    if channel == "discord":
        return bool(str(config.get("webhook_url") or "").strip())
    return bool(
        str(config.get("bot_token") or "").strip()
        and str(config.get("chat_id") or "").strip()
    )


def _discord_webhook(value: Any) -> str:
    webhook = str(value or "").strip()
    parsed = urlparse(webhook)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in DISCORD_HOSTS:
        raise NotificationDeliveryError("discord_webhook_invalid")
    if not DISCORD_PATH.fullmatch(parsed.path or "") or parsed.query or parsed.fragment:
        raise NotificationDeliveryError("discord_webhook_invalid")
    return webhook


def _telegram_credentials(token: Any, chat_id: Any = "") -> tuple[str, str]:
    normalized_token = str(token or "").strip()
    normalized_chat = str(chat_id or "").strip()
    if not TELEGRAM_TOKEN.fullmatch(normalized_token):
        raise NotificationDeliveryError("telegram_token_invalid")
    if normalized_chat and not TELEGRAM_CHAT_ID.fullmatch(normalized_chat):
        raise NotificationDeliveryError("telegram_chat_id_invalid")
    return normalized_token, normalized_chat


def _request_json(url: str, payload: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        method="POST" if payload is not None else "GET",
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "NoahAI-Notification/1"},
    )
    try:
        with urlopen(request, timeout=max(1.0, min(float(timeout), 15.0))) as response:
            raw = response.read(1_000_000)
            status = int(getattr(response, "status", 200) or 200)
    except HTTPError as exc:
        if exc.code in {401, 403, 404}:
            raise NotificationDeliveryError("notification_credential_rejected") from exc
        if exc.code == 429:
            raise NotificationDeliveryError("notification_rate_limited") from exc
        raise NotificationDeliveryError("notification_remote_error") from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise NotificationDeliveryError("notification_network_error") from exc
    if status < 200 or status >= 300:
        raise NotificationDeliveryError("notification_remote_error")
    if not raw:
        return {"ok": True}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NotificationDeliveryError("notification_response_invalid") from exc
    return value if isinstance(value, dict) else {"ok": True}


def _format_message(item: NotificationMessage) -> str:
    source = f" · {item.source.upper()}" if item.source else ""
    mode = str(item.execution_mode or "").strip().upper()
    mode_label = f"[{mode}]" if mode else ""
    occurred = item.occurred_at or datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    link = f"\n원격 상태 확인 (로그인 필요): https://daltrading.net/remote?source={item.source}" if item.source in SUPPORTED_VENUES and item.event_type in {'guardrail_stop','loss_warning','risk_data_unavailable','runtime_failure'} else ''
    return f"[NoahAI]{mode_label} {item.title}{source}\n{item.message}\n시각: {occurred}"[:3700] + link


def _deliver_discord(config: dict[str, Any], item: NotificationMessage, timeout: float) -> None:
    webhook = _discord_webhook(config.get("webhook_url"))
    separator = "&" if "?" in webhook else "?"
    content = _format_message(item)
    # Discord content limit is 2000; UTF-16 bounded preview also covers emoji.
    if len(content.encode('utf-16-le')) > 3800:
        content = content.encode('utf-16-le')[:3800].decode('utf-16-le', errors='ignore') + '\n… 긴 알림은 요약 표시합니다. 전체 내용은 앱 리포트·로그에서 확인하세요.'
    _request_json(f"{webhook}{separator}wait=true", {"content": content, "allowed_mentions": {"parse": []}}, timeout)


def _telegram_api(token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{token}/{method}"


def _deliver_telegram(config: dict[str, Any], item: NotificationMessage, timeout: float) -> None:
    token, chat_id = _telegram_credentials(config.get("bot_token"), config.get("chat_id"))
    if not chat_id:
        raise NotificationDeliveryError("telegram_chat_id_missing")
    result = _request_json(
        _telegram_api(token, "sendMessage"),
        {"chat_id": chat_id, "text": _format_message(item), "disable_web_page_preview": True},
        timeout,
    )
    if result.get("ok") is not True:
        raise NotificationDeliveryError("notification_credential_rejected")


def notification_status(settings: dict[str, Any] | None) -> dict[str, Any]:
    config = _configuration(settings)
    discord = _channel_config(settings, "discord")
    telegram = _channel_config(settings, "telegram")
    return {
        "enabled": bool(config.get("enabled", False)),
        "channels": {
            "discord": {
                "enabled": bool(discord.get("enabled", False)),
                "configured": bool(str(discord.get("webhook_url") or "").strip()),
            },
            "telegram": {
                "enabled": bool(telegram.get("enabled", False)),
                "configured": bool(str(telegram.get("bot_token") or "").strip() and str(telegram.get("chat_id") or "").strip()),
                "bot_configured": bool(str(telegram.get("bot_token") or "").strip()),
                "chat_configured": bool(str(telegram.get("chat_id") or "").strip()),
            },
        },
        "events": {
            key: bool(value)
            for key, value in dict(config.get("events") or {}).items()
            if key in SUPPORTED_EVENTS
        },
        "exchanges": {
            key: _source_enabled(config, key) for key in sorted(SUPPORTED_VENUES)
        },
    }


def test_notification_channel(settings: dict[str, Any], channel: str) -> dict[str, Any]:
    normalized = str(channel or "").strip().lower()
    if normalized not in SUPPORTED_CHANNELS:
        raise ValueError("지원하지 않는 알림 채널입니다.")
    config = _channel_config(settings, normalized)
    item = NotificationMessage(
        event_type="test",
        title="연결 테스트 성공",
        message="NoahAI 대시보드의 외부 알림 연결이 정상입니다. 이 메시지는 거래나 설정을 변경하지 않습니다.",
        severity="info",
    )
    timeout = float(_configuration(settings).get("timeout_seconds", 5) or 5)
    if normalized == "discord":
        _deliver_discord(config, item, timeout)
    else:
        _deliver_telegram(config, item, timeout)
    return {"ok": True, "channel": normalized, "checked_at": datetime.now(timezone.utc).isoformat()}


def discover_telegram_chats(settings: dict[str, Any]) -> dict[str, Any]:
    config = _channel_config(settings, "telegram")
    token, _ = _telegram_credentials(config.get("bot_token"))
    timeout = float(_configuration(settings).get("timeout_seconds", 5) or 5)
    identity = _request_json(_telegram_api(token, "getMe"), None, timeout)
    if identity.get("ok") is False:
        raise NotificationDeliveryError("notification_credential_rejected")
    updates = _request_json(_telegram_api(token, "getUpdates"), None, timeout)
    if updates.get("ok") is not True:
        raise NotificationDeliveryError("notification_remote_error")
    chats: dict[str, dict[str, str]] = {}
    for update in list(updates.get("result") or [])[-100:]:
        if not isinstance(update, dict):
            continue
        message = update.get("message") or update.get("channel_post") or update.get("my_chat_member")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat") if "chat" in message else message.get("chat", {})
        if not isinstance(chat, dict):
            continue
        chat_id = str(chat.get("id") or "").strip()
        if not TELEGRAM_CHAT_ID.fullmatch(chat_id):
            continue
        display = str(chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) or chat.get("username") or "개인 대화").strip()
        chats[chat_id] = {"chat_id": chat_id, "label": display[:120], "type": str(chat.get("type") or "private")[:24]}
    bot = identity.get("result") if isinstance(identity.get("result"), dict) else {}
    return {
        "ok": True,
        "bot": {"username": str(bot.get("username") or ""), "display_name": str(bot.get("first_name") or "")},
        "chats": list(chats.values()),
        "instruction": "Telegram에서 이 봇을 열어 시작(Start) 또는 /start를 보낸 뒤 다시 찾으세요.",
    }


class NotificationDispatcher:
    def __init__(self, *, max_queue: int = 200):
        self._queue: queue.Queue[tuple[int, NotificationMessage] | None] = queue.Queue(maxsize=max(10, int(max_queue)))
        self._lock = threading.RLock()
        self._settings: dict[str, Any] = {}
        self._last_sent: dict[str, float] = {}
        self._worker: threading.Thread | None = None
        self._stopping = False
        self._dropped = 0
        self._generation = 0
        self._scope = ""

    def configure(self, settings: dict[str, Any] | None, *, scope: str = "") -> None:
        with self._lock:
            next_settings = deepcopy(dict(settings or {}))
            next_scope = str(scope or "").strip()
            # Settings are account-local. Pending work from a prior generation
            # must be ignored after login/account or credential changes. An
            # unrelated settings save keeps the cooldown and queued messages.
            if next_scope != self._scope or _configuration(next_settings) != _configuration(self._settings):
                self._generation += 1
                self._last_sent.clear()
            self._settings = next_settings
            self._scope = next_scope
            config = _configuration(self._settings)
            should_run = bool(config.get("enabled", False)) and any(
                _channel_ready(self._settings, channel)
                for channel in SUPPORTED_CHANNELS
            )
            if should_run and (self._worker is None or not self._worker.is_alive()):
                self._stopping = False
                self._worker = threading.Thread(target=self._run, name="NoahAI-Notifications", daemon=True)
                self._worker.start()

    def publish(self, item: NotificationMessage) -> bool:
        if item.event_type not in SUPPORTED_EVENTS:
            return False
        with self._lock:
            settings = deepcopy(self._settings)
            generation = self._generation
        config = _configuration(settings)
        if (
            not bool(config.get("enabled", False))
            or not _event_enabled(config, item.event_type)
            or not _source_enabled(config, item.source)
            or not any(_channel_ready(settings, channel) for channel in SUPPORTED_CHANNELS)
        ):
            return False
        dedupe = item.dedupe_key or f"{item.event_type}:{item.source}:{item.title}"
        cooldown = _bounded_int(config.get("cooldown_seconds"), 300, 86400)
        now = time.monotonic()
        with self._lock:
            if generation != self._generation:
                return False
            if cooldown and dedupe in self._last_sent and now - self._last_sent[dedupe] < cooldown:
                return False
            self._last_sent[dedupe] = now
        try:
            self._queue.put_nowait((generation, item))
            return True
        except queue.Full:
            with self._lock:
                self._dropped += 1
                if generation == self._generation:
                    self._last_sent.pop(dedupe, None)
            LOGGER.warning("NoahAI 외부 알림 큐가 가득 차 메시지 1건을 건너뜁니다.")
            return False

    def _run(self) -> None:
        while True:
            try:
                envelope = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if envelope is None:
                self._queue.task_done()
                break
            try:
                generation, item = envelope
                self._deliver(item, generation=generation)
            except Exception as exc:
                LOGGER.warning("외부 알림 처리 실패 (%s); 다음 메시지 처리는 계속합니다.", type(exc).__name__)
            finally:
                self._queue.task_done()

    def _deliver(self, item: NotificationMessage, *, generation: int | None = None) -> None:
        with self._lock:
            if generation is None:
                generation = self._generation
            if self._stopping or generation != self._generation:
                return
            # Validate generation and capture destination in ONE critical
            # section. Never read another account's credentials for this item.
            settings = deepcopy(self._settings)
        config = _configuration(settings)
        if not config.get("enabled", False) or not _event_enabled(config, item.event_type) or not _source_enabled(config, item.source):
            return
        timeout = float(config.get("timeout_seconds", 5) or 5)
        retry_count = _bounded_int(config.get("retry_count"), 2, 3)
        for channel in sorted(SUPPORTED_CHANNELS):
            channel_config = _channel_config(settings, channel)
            if not bool(channel_config.get("enabled", False)):
                continue
            for attempt in range(retry_count + 1):
                with self._lock:
                    if self._stopping or generation != self._generation:
                        return
                try:
                    if channel == "discord":
                        _deliver_discord(channel_config, item, timeout)
                    else:
                        _deliver_telegram(channel_config, item, timeout)
                    break
                except NotificationDeliveryError as exc:
                    if attempt >= retry_count or str(exc) in {
                        "discord_webhook_invalid", "telegram_token_invalid",
                        "telegram_chat_id_invalid", "telegram_chat_id_missing",
                        "notification_credential_rejected",
                    }:
                        LOGGER.warning("%s 알림 전송 실패 (%s)", channel, str(exc))
                        break
                    time.sleep(min(2.0, 0.4 * (2 ** attempt)))

    def shutdown(self, timeout: float = 1.5) -> None:
        self._stopping = True
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=max(0.0, float(timeout)))


_DISPATCHER = NotificationDispatcher()


def configure_notifications(settings: dict[str, Any] | None, *, scope: str = "") -> None:
    _DISPATCHER.configure(settings, scope=scope)


def publish_notification(
    event_type: str,
    title: str,
    message: str,
    *,
    source: str = "",
    execution_mode: str = "",
    severity: str = "info",
    dedupe_key: str = "",
) -> bool:
    return _DISPATCHER.publish(NotificationMessage(
        event_type=str(event_type or "").strip(),
        title=str(title or "NoahAI 알림").strip()[:160],
        message=str(message or "").strip()[:3200],
        source=str(source or "").strip().lower()[:32],
        execution_mode=str(execution_mode or "").strip().lower()[:16],
        severity=str(severity or "info").strip().lower()[:16],
        dedupe_key=str(dedupe_key or "").strip()[:200],
        occurred_at=datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    ))


def publish_market_regime_change(source: str, previous: str | None, current: str | None) -> bool:
    """Publish a semantic transition, never an initial observation or retry.

    Reselection can remain pending over many observation cycles. Its lifetime
    is independent of a stabilized market regime transition.
    """
    old = str(previous or "").strip().lower()
    new = str(current or "").strip().lower()
    venue = str(source or "").strip().lower()
    if not old or not new or old == new or old == "unknown" or new == "unknown":
        return False
    return publish_notification(
        "market_regime_change", "시장국면 변화 감지",
        f"{venue.upper()} 시장국면이 {old}에서 {new}(으)로 변경되었습니다. 신규 후보와 기존 포지션의 위험 조건을 확인하세요.",
        source=venue, severity="warning", dedupe_key=f"regime:{venue}:{old}:{new}",
    )


def publish_stock_risk_decision(source: str, execution_mode: str, decision: dict,
                                *, warning_percent: float = 5) -> bool:
    """Use broker policy evidence; PAPER and missing percentages are not LIVE losses."""
    if execution_mode not in {'live', 'live_api'}:
        return False
    metrics = decision.get('metrics') or {}
    reasons = decision.get('reasons') or []
    venue = normalize_venue(source)
    if metrics.get('pnl_verified') is False or 'risk_data_unavailable' in reasons:
        event, title, message = ('risk_data_unavailable', 'LIVE 증권 위험 데이터 확인 실패',
            '당일 손익 또는 위험 근거를 확인하지 못했습니다. 0원으로 추정하지 않고 신규 진입을 보류합니다. 기존 포지션 관리와 실시간 로그를 확인하세요.')
    elif decision.get('allowed') is False:
        event, title, message = ('guardrail_stop', 'LIVE 증권 가드레일 차단',
            '해당 증권사의 위험·주문 정책이 주문을 차단했습니다. 구체적인 한도와 사유는 실시간 로그에서 확인하세요. 임의 청산이나 권한 변경은 하지 않습니다.')
    else:
        try:
            rate = float(metrics['loss_rate'])
            threshold = float(warning_percent)
        except (KeyError, TypeError, ValueError):
            return False
        if not math.isfinite(rate) or not math.isfinite(threshold) or rate < max(0.1, threshold):
            return False
        event, title, message = ('loss_warning', 'LIVE 증권 손실 경고',
            f"확인된 손실률 {rate:.2f}%가 알림 기준 {threshold:.2f}%에 도달했습니다. 산출 기준: {str(metrics.get('loss_basis') or '증권 위험 판정')[:80]}. 기관별 위험 한도는 별도로 적용됩니다.")
    return publish_notification(event, title, message, source=venue, execution_mode='live',
        severity='warning' if event != 'guardrail_stop' else 'critical', dedupe_key=f'stock-risk:{venue}:{event}')


def publish_runtime_failure(source: str, error: Exception) -> bool:
    try:
        return publish_notification('runtime_failure', '거래 실행 주기 오류',
            f'실행 중 오류({type(error).__name__})가 발생했습니다. 연결·시세·종목 조회 상태와 실시간 로그를 확인하세요.',
            source=source, severity='error', dedupe_key=f'cycle:{normalize_venue(source)}:{type(error).__name__}')
    except Exception:
        return False


def shutdown_notifications(timeout: float = 1.5) -> None:
    _DISPATCHER.shutdown(timeout=timeout)
