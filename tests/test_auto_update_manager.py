import json
from pathlib import Path

from utils.auto_update_manager import AutoUpdateManager


def test_version_normalization_orders_properly():
    a = AutoUpdateManager._normalize_version("v3.8.9.24")
    b = AutoUpdateManager._normalize_version("v3.8.9.25")
    assert b > a


def test_apply_pending_update_returns_false_without_windows_runtime(tmp_path, monkeypatch):
    mgr = AutoUpdateManager(settings={"ui_settings": {"auto_update_auto_apply_on_exit": True}})
    fake_update = tmp_path / "AITrading.exe"
    fake_update.write_bytes(b"dummy")
    mgr.pending_update = {
        "downloaded": True,
        "asset_path": str(fake_update),
        "latest_version": "3.8.9.99",
    }

    monkeypatch.setattr("sys.platform", "darwin")
    assert mgr.apply_pending_update_and_restart() is False


def test_has_pending_update_flag():
    mgr = AutoUpdateManager(settings={})
    assert mgr.has_pending_update() is False
    mgr.pending_update = {"downloaded": True}
    assert mgr.has_pending_update() is True


def test_resolve_install_target_prefers_persisted_when_running_from_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "auto_updater"
    cache_dir.mkdir(parents=True, exist_ok=True)
    marker_path = tmp_path / "config" / "auto_update_target.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    persisted_target = tmp_path / "Desktop" / "AITrading.exe"
    persisted_target.parent.mkdir(parents=True, exist_ok=True)
    persisted_target.write_bytes(b"old")

    marker_path.write_text(
        json.dumps({"install_target_exe": str(persisted_target)}, ensure_ascii=False),
        encoding="utf-8",
    )

    current_cache_exe = cache_dir / "3.8.9.25" / "AITrading.new.exe"
    current_cache_exe.parent.mkdir(parents=True, exist_ok=True)
    current_cache_exe.write_bytes(b"new")

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(current_cache_exe))

    mgr = AutoUpdateManager(settings={})
    resolved = mgr._resolve_install_target_executable()
    assert resolved == persisted_target


def test_download_uses_staged_name_in_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "auto_updater"
    marker_path = tmp_path / "config" / "auto_update_target.json"

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)

    mgr = AutoUpdateManager(settings={})

    def _fake_download(url, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"binary")
        return True

    monkeypatch.setattr(mgr, "_download_file", _fake_download)
    monkeypatch.setattr(mgr, "_fetch_expected_sha_from_manifest", lambda assets: "")

    release = {
        "tag_name": "v3.8.9.30",
        "assets": [
            {
                "name": "AITrading.exe",
                "browser_download_url": "https://example.com/AITrading.exe",
            }
        ],
    }

    result = mgr.download_latest_update(release_payload=release)
    assert result["ok"] is True
    assert result["asset_path"].endswith("AITrading.new.exe")
    assert Path(result["asset_path"]).exists()
