#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import multiprocessing
from pathlib import Path
import time
import builtins

import pytest

from config import settings as settings_module


def _hold_account_settings_lock(config_dir: str, ready, hold_seconds: float) -> None:
    import path_utils
    from config import settings as child_settings

    path_utils.get_config_dir = lambda: config_dir
    with child_settings._settings_interprocess_lock(timeout_seconds=5.0):
        ready.set()
        time.sleep(hold_seconds)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_save_settings_creates_backup_when_existing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"version": 1, "name": "old"})

    assert settings_module.save_settings({"version": 2, "name": "new"}) is True
    assert _read_json(settings_path)["version"] == 2

    backups = settings_module.list_settings_backups(limit=10)
    assert len(backups) == 1
    backup_payload = _read_json(Path(backups[0]))
    assert backup_payload["version"] == 1


def test_backup_retention_keeps_latest_three(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"seq": 0})

    # 기존 파일이 있을 때 save_settings는 저장 전 자동 백업을 만든다.
    for i in range(1, 7):
        assert settings_module.save_settings({"seq": i}) is True

    backups = settings_module.list_settings_backups(limit=20)
    assert len(backups) == 3

    # 최신 3개 백업은 직전 seq 값(5,4,3)을 포함해야 한다.
    seq_values = [_read_json(Path(p))["seq"] for p in backups]
    assert set(seq_values) == {3, 4, 5}


def test_restore_settings_from_backup_replaces_current_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"mode": "before"})

    assert settings_module.save_settings({"mode": "after"}) is True
    backups = settings_module.list_settings_backups(limit=5)
    assert backups

    # 첫 백업은 before 상태
    assert settings_module.restore_settings_from_backup(backups[0]) is True
    assert _read_json(settings_path)["mode"] == "before"


def test_failed_atomic_replace_preserves_existing_settings_and_reports_reason(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"mode": "before"})

    def deny_replace(source, destination):
        raise PermissionError("simulated Windows controlled-folder denial")

    monkeypatch.setattr(settings_module.os, "replace", deny_replace)

    assert settings_module.save_settings({"mode": "after"}) is False
    assert settings_module.get_last_settings_save_error() == "permission_denied"
    assert settings_module.get_last_settings_save_diagnostics() == {
        "code": "permission_denied",
        "stage": "replace_canonical",
        "error_type": "PermissionError",
        "errno": None,
        "winerror": None,
    }
    assert _read_json(settings_path)["mode"] == "before"
    assert list(tmp_path.glob(".settings-*.tmp")) == []


def test_background_path_patch_preserves_newer_unrelated_user_settings(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {
        "verbose_trade_logging": True,
        "enabled_exchanges": ["upbit"],
        "analyzer_settings": {"user_signal_threshold": 50},
    })

    assert settings_module.patch_settings_paths({
        "analyzer_settings.user_signal_threshold": 61,
    }) is True

    persisted = _read_json(settings_path)
    assert persisted["verbose_trade_logging"] is True
    assert persisted["enabled_exchanges"] == ["upbit"]
    assert persisted["analyzer_settings"]["user_signal_threshold"] == 61


def test_path_patch_does_not_report_success_when_fresh_read_disagrees(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    reads = iter([
        {"verbose_trade_logging": False},
        {"verbose_trade_logging": False},
    ])
    monkeypatch.setattr(settings_module, "load_settings", lambda **kwargs: next(reads))
    monkeypatch.setattr(settings_module, "_save_settings_unlocked", lambda payload: True)

    assert settings_module.patch_settings_paths({"verbose_trade_logging": True}) is False
    assert settings_module.get_last_settings_save_error() == "verification_failed"
    assert settings_module.get_last_settings_save_diagnostics()["stage"] == "verify_canonical"


def test_windows_sharing_violation_is_reported_as_file_locked(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"mode": "before"})

    class SharingViolation(OSError):
        winerror = 32

    monkeypatch.setattr(
        settings_module.os,
        "replace",
        lambda _source, _destination: (_ for _ in ()).throw(SharingViolation("locked")),
    )
    monkeypatch.setattr(
        settings_module,
        "_windows_replace_compatibility_error",
        lambda _error: False,
    )
    # Avoid waiting five real seconds while preserving the terminal replace path.
    monotonic_values = iter([0.0, 0.0, 6.0])
    monkeypatch.setattr(settings_module.time, "monotonic", lambda: next(monotonic_values))

    assert settings_module.save_settings({"mode": "after"}) is False
    diagnostic = settings_module.get_last_settings_save_diagnostics()
    assert diagnostic["code"] == "file_locked"
    assert diagnostic["stage"] == "replace_canonical"
    assert diagnostic["winerror"] == 32
    assert _read_json(settings_path)["mode"] == "before"


def test_windows_replace_sharing_rule_falls_back_to_verified_legacy_write(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"mode": "before", "preserved": True})

    class SharingViolation(OSError):
        winerror = 32

    monkeypatch.setattr(
        settings_module.os,
        "replace",
        lambda _source, _destination: (_ for _ in ()).throw(SharingViolation("locked")),
    )
    monkeypatch.setattr(
        settings_module,
        "_windows_replace_compatibility_error",
        lambda error: getattr(error, "winerror", None) in {5, 32, 33},
    )
    monotonic_values = iter([0.0, 0.0, 6.0])
    monkeypatch.setattr(settings_module.time, "monotonic", lambda: next(monotonic_values))

    assert settings_module.save_settings({"mode": "after", "preserved": True}) is True
    assert settings_module.get_last_settings_save_error() == ""
    assert settings_module.get_last_settings_save_method() == "in_place_compat"
    persisted = _read_json(settings_path)
    assert persisted["mode"] == "after"
    assert persisted["preserved"] is True
    assert list(tmp_path.glob(".settings-*.tmp")) == []


def test_settings_save_uses_account_scoped_interprocess_lock(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))

    assert settings_module.save_settings({"mode": "saved"}) is True
    assert settings_module.get_last_settings_save_method() == "atomic_replace"
    assert (tmp_path / "settings.json.lock").is_file()
    assert _read_json(tmp_path / "settings.json")["mode"] == "saved"


def test_committed_save_is_not_rejected_when_windows_console_cannot_encode_output(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    real_print = builtins.print

    def legacy_console_print(*values, **kwargs):
        message = " ".join(str(value) for value in values)
        if any(ord(character) > 127 for character in message):
            raise UnicodeEncodeError("cp949", message, 0, 1, "simulated legacy console")
        return real_print(*values, **kwargs)

    monkeypatch.setattr(builtins, "print", legacy_console_print)

    assert settings_module.save_settings({"mode": "saved", "label": "한글"}) is True
    assert settings_module.get_last_settings_save_error() == ""
    assert _read_json(tmp_path / "settings.json")["label"] == "한글"


def test_unicode_encode_error_is_not_misclassified_as_invalid_settings_data():
    error = UnicodeEncodeError("cp949", "✅", 0, 1, "simulated legacy console")
    assert settings_module._settings_save_error_code(error) == "write_failed"


def test_settings_load_does_not_fall_back_when_status_glyph_cannot_be_encoded(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    _write_json(tmp_path / "settings.json", {"mode": "persisted", "label": "한글"})
    real_print = builtins.print

    def legacy_console_print(*values, **kwargs):
        message = " ".join(str(value) for value in values)
        if any(ord(character) > 127 for character in message):
            raise UnicodeEncodeError("cp949", message, 0, 1, "simulated legacy console")
        return real_print(*values, **kwargs)

    monkeypatch.setattr(builtins, "print", legacy_console_print)

    loaded = settings_module.load_settings(persist_migrations=False)

    assert loaded["mode"] == "persisted"
    assert loaded["label"] == "한글"


@pytest.mark.parametrize(
    ("source_encoding", "encode"),
    [
        ("utf-8-sig", lambda text: b"\xef\xbb\xbf" + text.encode("utf-8")),
        ("utf-16", lambda text: text.encode("utf-16")),
        ("cp949", lambda text: text.encode("cp949")),
    ],
)
def test_legacy_windows_settings_encoding_preserves_credentials_and_normalizes(
    tmp_path, monkeypatch, source_encoding, encode,
):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    payload = {
        "marker": "기존 한글 설정",
        "binance_api_key": "TEST-NOT-A-SECRET",
        "binance_secret_key": "TEST-NOT-A-SECRET-EITHER",
    }
    original = encode(json.dumps(payload, ensure_ascii=False))
    settings_path.write_bytes(original)

    read_only = settings_module.load_settings(persist_migrations=False)
    assert read_only["marker"] == payload["marker"]
    assert read_only["binance_api_key"] == payload["binance_api_key"]
    assert settings_path.read_bytes() == original

    migrated = settings_module.load_settings(persist_migrations=True)
    assert migrated["marker"] == payload["marker"]
    assert migrated["binance_secret_key"] == payload["binance_secret_key"]
    canonical = settings_path.read_bytes()
    assert not canonical.startswith(b"\xef\xbb\xbf")
    persisted = json.loads(canonical.decode("utf-8"))
    assert persisted["marker"] == payload["marker"]
    assert persisted["binance_api_key"] == payload["binance_api_key"]
    assert settings_module.get_last_settings_save_error() == ""


def test_unreadable_existing_settings_blocks_overwrite_and_preserves_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    original = b'{"marker":"preserve-me"}\xff'
    settings_path.write_bytes(original)

    assert settings_module.save_settings({"marker": "replacement"}) is False
    assert settings_path.read_bytes() == original
    assert settings_module.get_last_settings_save_error() == "settings_file_unreadable"
    assert settings_module.get_last_settings_save_diagnostics()["stage"] == "validate_existing"
    assert settings_module.list_settings_backups(limit=10) == []


def test_unreadable_settings_load_exposes_secret_free_storage_status(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    settings_path.write_bytes(b'{"binance_api_key":"DO-NOT-LOG"}\xff')

    loaded = settings_module.load_settings(persist_migrations=False)
    diagnostic = settings_module.get_last_settings_load_diagnostics()

    assert isinstance(loaded, dict)
    assert diagnostic == {
        "ok": False,
        "code": "settings_file_unreadable",
        "error_type": "SettingsFileUnreadableError",
    }
    assert "DO-NOT-LOG" not in json.dumps(diagnostic)


def test_restore_rejects_unreadable_backup_without_touching_current(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    settings_path = tmp_path / "settings.json"
    _write_json(settings_path, {"marker": "current"})
    invalid_backup = tmp_path / "invalid-backup.json"
    invalid_backup.write_bytes(b'{"marker":"broken"}\xff')

    assert settings_module.restore_settings_from_backup(str(invalid_backup)) is False
    assert _read_json(settings_path)["marker"] == "current"
    assert settings_module.get_last_settings_save_error() == "settings_file_unreadable"
    assert settings_module.get_last_settings_save_diagnostics()["stage"] == "validate_backup"


def test_restore_cp949_backup_writes_canonical_utf8_in_korean_path(tmp_path, monkeypatch):
    config_dir = tmp_path / "한글 사용자" / "설정"
    config_dir.mkdir(parents=True)
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(config_dir))
    settings_path = config_dir / "settings.json"
    _write_json(settings_path, {"marker": "current"})
    backup_path = tmp_path / "이전 설정.json"
    backup_path.write_bytes(json.dumps({"marker": "복구됨"}, ensure_ascii=False).encode("cp949"))

    assert settings_module.restore_settings_from_backup(str(backup_path)) is True
    canonical = settings_path.read_bytes()
    assert json.loads(canonical.decode("utf-8"))["marker"] == "복구됨"
    assert not canonical.startswith(b"\xef\xbb\xbf")


def test_settings_save_waits_for_another_process_writer(tmp_path, monkeypatch):
    monkeypatch.setattr("path_utils.get_config_dir", lambda: str(tmp_path))
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    holder = context.Process(
        target=_hold_account_settings_lock,
        args=(str(tmp_path), ready, 0.8),
    )
    holder.start()
    try:
        assert ready.wait(timeout=5.0)
        started = time.monotonic()
        assert settings_module.save_settings({"mode": "after-contention"}) is True
        elapsed = time.monotonic() - started
    finally:
        holder.join(timeout=5.0)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=5.0)

    assert holder.exitcode == 0
    assert elapsed >= 0.55
    assert _read_json(tmp_path / "settings.json")["mode"] == "after-contention"


def test_evaluator_coin_persistence_uses_path_merge_without_private_backup(monkeypatch):
    from trading.evaluator import Evaluator

    calls = []
    monkeypatch.setattr(settings_module, "patch_settings_paths", lambda changes: calls.append(changes) or True)

    class Logger:
        def info(self, *_args, **_kwargs):
            pass

        def error(self, *_args, **_kwargs):
            pass

    evaluator = object.__new__(Evaluator)
    evaluator.logger = Logger()
    evaluator._update_env_coins(["btcusdt", "ETHUSDT"])

    assert calls == [{
        "selected_coins": ["BTCUSDT", "ETHUSDT"],
        "coin_allocation": {"BTCUSDT": 20, "ETHUSDT": 20},
    }]
    source = (Path(__file__).resolve().parents[1] / "trading" / "evaluator.py").read_text(encoding="utf-8")
    method = source[source.index("    def _update_env_coins"):source.index("    def _verify_data_consistency")]
    assert "open(env_file" not in method
    assert "shutil.copy2" not in method
