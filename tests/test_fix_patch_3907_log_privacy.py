from pathlib import Path

import psutil

from utils import runtime_stability
from utils.log_safety import (
    LOG_BACKUP_COUNT,
    LOG_MAX_BYTES,
    membership_log_summary,
    status_response_log_summary,
)


ROOT = Path(__file__).resolve().parents[1]


def test_login_and_status_log_summaries_exclude_account_secrets() -> None:
    payload = {
        "id": "private-user",
        "email": "private@example.test",
        "session_id": "private-session-id",
        "access_token": "private-bearer-token",
        "user_grade": "referral",
        "membership_policy": {
            "policy_version": "policy-v1",
            "allowed_exchanges": [],
            "referral_programs": [
                {
                    "exchange": "binance",
                    "attribution_status": "required",
                    "referral_code": "private-code",
                    "referral_url": "https://example.test/private",
                    "uid_masked": "****1234",
                    "verification_error": "private-error",
                },
                {"exchange": "bybit", "attribution_status": "pending"},
            ],
        },
        "is_active": True,
        "force_quit": False,
    }

    membership = membership_log_summary(payload)
    status = status_response_log_summary(payload)
    rendered = f"{membership} {status}"

    for secret in (
        "private-user",
        "private@example.test",
        "private-session-id",
        "private-bearer-token",
        "private-code",
        "https://example.test/private",
        "****1234",
        "private-error",
    ):
        assert secret not in rendered
    assert membership["referral_status_counts"] == {"pending": 1, "required": 1}
    assert status["access_token_refreshed"] is True


def test_windows_pid_probe_uses_psutil_without_os_kill(monkeypatch) -> None:
    monkeypatch.setattr(runtime_stability.sys, "platform", "win32")
    monkeypatch.setattr(psutil, "pid_exists", lambda pid: int(pid) == 321)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("os.kill must not be used for the Windows PID probe")

    monkeypatch.setattr(runtime_stability.os, "kill", fail_if_called)
    assert runtime_stability._process_is_running(321) is True
    assert runtime_stability._process_is_running(654) is False


def test_active_logs_are_rotated_instead_of_deleted() -> None:
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    initialize_logs = main_source.split("    def initialize_logs", 1)[1].split(
        "    def initialize_theme_config", 1
    )[0]

    assert "os.remove(" not in initialize_logs
    assert "rotation=LOG_ROTATION_SIZE" in main_source
    assert "maxBytes=LOG_MAX_BYTES" in main_source
    assert LOG_MAX_BYTES == 25 * 1024 * 1024
    assert LOG_BACKUP_COUNT == 7


def test_login_sources_do_not_dump_raw_auth_payloads() -> None:
    main_source = (ROOT / "main.py").read_text(encoding="utf-8")
    login_source = (ROOT / "ui" / "login_modern.py").read_text(encoding="utf-8")
    status_source = (ROOT / "user_status_manager.py").read_text(encoding="utf-8")

    assert "user_info 내용:" not in main_source
    assert "access_token 추가:" not in main_source
    assert "로그인 성공 응답: {response_data}" not in login_source
    assert "서버 응답 데이터: {data}" not in status_source
    assert "SESSION_ID={session_id" not in status_source
