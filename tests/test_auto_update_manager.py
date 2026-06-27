from pathlib import Path

from utils.auto_update_manager import AutoUpdateManager


def test_version_normalization_orders_properly():
    a = AutoUpdateManager._normalize_version("v3.8.9.23")
    b = AutoUpdateManager._normalize_version("v3.8.9.24")
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
