#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path

from config import settings as settings_module


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
