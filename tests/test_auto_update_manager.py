import json
import hashlib
from pathlib import Path
from unittest.mock import Mock

from utils.auto_update_manager import AutoUpdateManager


def test_version_normalization_orders_properly():
    a = AutoUpdateManager._normalize_version("v3.8.9.24")
    b = AutoUpdateManager._normalize_version("v3.8.9.25")
    assert b > a


def test_same_version_changed_manifest_sha_is_a_fix_patch_update(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    marker_path = tmp_path / "config" / "target.json"
    installed = tmp_path / "AITrading.exe"
    installed.write_bytes(b"fix-patch-1")
    remote_sha = hashlib.sha256(b"fix-patch-2").hexdigest()

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_executable", lambda self: installed)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)

    mgr = AutoUpdateManager(settings={"ui_settings": {"auto_update_auto_download": False}})
    monkeypatch.setattr(mgr, "_get_current_version", lambda: "3.9.0.5")
    monkeypatch.setattr(
        mgr,
        "_fetch_latest_release",
        lambda: {
            "tag_name": "v3.9.0.5",
            "html_url": "https://example.test/release",
            "assets": [{"name": "release-manifest.json"}],
            "_repo": "example/repo",
        },
    )
    monkeypatch.setattr(
        mgr,
        "_fetch_verification_policy_from_manifest",
        lambda _assets: {"sha256": remote_sha, "sha256_required": True, "authenticode_required": False},
    )

    result = mgr.check_for_updates()
    assert result["update_available"] is True
    assert result["update_reason"] == "same_version_asset_changed"
    assert result["installed_sha256"] == hashlib.sha256(b"fix-patch-1").hexdigest()
    assert result["release_sha256"] == remote_sha


def test_same_version_matching_manifest_sha_is_not_re_downloaded(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    marker_path = tmp_path / "config" / "target.json"
    installed = tmp_path / "AITrading.exe"
    installed.write_bytes(b"fix-patch-2")
    installed_sha = hashlib.sha256(installed.read_bytes()).hexdigest()

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_executable", lambda self: installed)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)

    mgr = AutoUpdateManager(settings={"ui_settings": {"auto_update_auto_download": False}})
    monkeypatch.setattr(mgr, "_get_current_version", lambda: "3.9.0.5")
    monkeypatch.setattr(
        mgr,
        "_fetch_latest_release",
        lambda: {
            "tag_name": "v3.9.0.5",
            "assets": [{"name": "release-manifest.json"}],
        },
    )
    monkeypatch.setattr(
        mgr,
        "_fetch_verification_policy_from_manifest",
        lambda _assets: {"sha256": installed_sha, "sha256_required": True, "authenticode_required": False},
    )

    result = mgr.check_for_updates()
    assert result["update_available"] is False
    assert result["update_reason"] == ""


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
    mgr.pending_update = {}
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


def test_cache_marker_is_rejected_even_when_it_points_to_another_cache_root(tmp_path, monkeypatch):
    active_cache = tmp_path / "local" / "cache" / "auto_updater"
    active_cache.mkdir(parents=True, exist_ok=True)
    marker_path = tmp_path / "data" / "config" / "auto_update_target.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    stale_cache_exe = tmp_path / "documents" / "cache" / "auto_updater" / "3.8.9.27" / "AITrading.new.exe"
    stale_cache_exe.parent.mkdir(parents=True, exist_ok=True)
    stale_cache_exe.write_bytes(b"staged")
    marker_path.write_text(
        json.dumps({"install_target_exe": str(stale_cache_exe)}, ensure_ascii=False),
        encoding="utf-8",
    )

    current_cache_exe = active_cache / "3.8.9.30" / "AITrading.new.exe"
    current_cache_exe.parent.mkdir(parents=True, exist_ok=True)
    current_cache_exe.write_bytes(b"new")

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: active_cache)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(current_cache_exe))

    mgr = AutoUpdateManager(settings={})
    assert mgr.install_target_exe == current_cache_exe
    assert AutoUpdateManager._looks_like_update_cache_path(stale_cache_exe) is True


def test_recovers_stable_target_from_previous_apply_script(tmp_path, monkeypatch):
    active_cache = tmp_path / "local" / "cache" / "auto_updater"
    active_cache.mkdir(parents=True, exist_ok=True)
    marker_path = tmp_path / "data" / "config" / "auto_update_target.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)

    current_cache_exe = active_cache / "3.8.9.30" / "AITrading.new.exe"
    current_cache_exe.parent.mkdir(parents=True, exist_ok=True)
    current_cache_exe.write_bytes(b"new")

    stable_target = tmp_path / "Desktop" / "noah" / "AITrading.exe"
    stable_target.parent.mkdir(parents=True, exist_ok=True)
    stable_target.write_bytes(b"installed")

    historical_cache = marker_path.parent.parent / "cache" / "auto_updater"
    historical_cache.mkdir(parents=True, exist_ok=True)
    (historical_cache / "apply_update_3.8.9.29.ps1").write_text(
        f"$target = '{stable_target}'\n$newExe = 'ignored'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: active_cache)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(current_cache_exe))

    mgr = AutoUpdateManager(settings={})
    assert mgr.install_target_exe == stable_target
    saved = json.loads(marker_path.read_text(encoding="utf-8"))
    assert Path(saved["install_target_exe"]) == stable_target


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
    import hashlib
    binary_sha = hashlib.sha256(b"binary").hexdigest()
    monkeypatch.setattr(
        mgr,
        "_fetch_verification_policy_from_manifest",
        lambda assets: {
            "sha256": binary_sha,
            "sha256_required": True,
            "authenticode_required": False,
            "source": "github_release_manifest",
        },
    )

    release = {
        "tag_name": "v3.8.9.30",
        "assets": [
            {
                "name": "AITrading.exe",
                "browser_download_url": "https://github.com/example/repo/releases/download/v3.8.9.30/AITrading.exe",
            }
        ],
    }

    result = mgr.download_latest_update(release_payload=release)
    assert result["ok"] is True
    assert result["asset_path"].endswith("AITrading.new.exe")
    assert Path(result["asset_path"]).exists()


def test_download_fails_closed_without_release_manifest_sha(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    marker_path = tmp_path / "config" / "target.json"
    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    mgr = AutoUpdateManager(settings={})
    monkeypatch.setattr(
        mgr,
        "_download_file",
        lambda _url, output: (output.parent.mkdir(parents=True, exist_ok=True), output.write_bytes(b"x"), True)[-1],
    )
    monkeypatch.setattr(mgr, "_fetch_verification_policy_from_manifest", lambda _assets: {})
    result = mgr.download_latest_update({
        "tag_name": "v9.9.9",
        "assets": [{"name": "AITrading.exe", "browser_download_url": "https://github.com/example/repo/releases/download/v9.9.9/app.exe"}],
    })
    assert result == {"ok": False, "reason": "release_manifest_or_sha256_missing"}


def test_update_transaction_is_persisted_and_restores_pending(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    marker_path = tmp_path / "config" / "target.json"
    asset = cache_dir / "3.9.1" / "AITrading.new.exe"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"signed-binary-placeholder")
    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    mgr = AutoUpdateManager(settings={})
    mgr._write_transaction(
        "downloaded",
        old_version="3.9.0.2",
        new_version="3.9.1",
        asset_path=str(asset),
        sha256=AutoUpdateManager._sha256_file(asset),
    )
    restored = AutoUpdateManager(settings={})
    assert restored.has_pending_update() is True
    assert restored.pending_update["latest_version"] == "3.9.1"


def test_apply_script_requires_backup_sha_and_postcheck_without_certificate():
    script = AutoUpdateManager._build_apply_script(
        target_exe="C:/NoahAI/AITrading.exe",
        new_exe="C:/NoahAI/cache/AITrading.new.exe",
        backup_exe="C:/NoahAI/AITrading.exe.bak",
        journal_path="C:/NoahAI/update.json",
        expected_sha="a" * 64,
        old_version="3.9.0.2",
        new_version="3.9.0.3",
    )
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "Get-AuthenticodeSignature" not in script
    assert "backup failed" in script
    assert "Set-Phase 'postcheck_pending'" in script


def test_unsigned_policy_rejects_non_github_download_url(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    marker_path = tmp_path / "config" / "target.json"
    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    mgr = AutoUpdateManager(settings={})
    result = mgr.download_latest_update({
        "tag_name": "v9.9.9",
        "assets": [{"name": "AITrading.exe", "browser_download_url": "http://example.test/app.exe"}],
    })
    assert result == {"ok": False, "reason": "untrusted_release_url"}


def _windows_update_manager(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache" / "auto_updater"
    marker_path = tmp_path / "config" / "auto_update_target.json"
    target = tmp_path / "installed" / "AITrading.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old-executable")
    asset = cache_dir / "3.9.0.8" / "AITrading.new.exe"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"new-executable")
    monkeypatch.setattr(AutoUpdateManager, "_resolve_update_cache_dir", lambda self: cache_dir)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_marker_path", lambda self: marker_path)
    monkeypatch.setattr(AutoUpdateManager, "_resolve_install_target_executable", lambda self: target)
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    manager = AutoUpdateManager(settings={"ui_settings": {"auto_update_auto_apply_on_exit": True}})
    manager.pending_update = {
        "downloaded": True,
        "asset_path": str(asset),
        "latest_version": "3.9.0.8",
        "sha256": AutoUpdateManager._sha256_file(asset),
    }
    manager._write_transaction(
        "downloaded",
        old_version="3.9.0.8",
        new_version="3.9.0.8",
        asset_path=str(asset),
        target_path=str(target),
        sha256=manager.pending_update["sha256"],
    )
    return manager, target, asset


def test_apply_consumes_pre_shutdown_approval_without_second_exchange_query(tmp_path, monkeypatch):
    manager, _target, _asset = _windows_update_manager(tmp_path, monkeypatch)
    preflight = Mock(return_value={"ok": True, "expected_positions": []})
    manager.set_safety_callbacks(preflight_callback=lambda _action: preflight())
    popen = Mock()
    monkeypatch.setattr("utils.auto_update_manager.subprocess.Popen", popen)

    approval = manager.authorize_pending_update()
    manager.record_shutdown_result(True)

    assert approval["ok"] is True
    assert manager.apply_pending_update_and_restart() is True
    assert preflight.call_count == 1
    assert manager.transaction["phase"] == "apply_scheduled"
    assert popen.call_count == 1


def test_apply_without_pre_shutdown_approval_fails_closed(tmp_path, monkeypatch):
    manager, _target, _asset = _windows_update_manager(tmp_path, monkeypatch)
    manager.record_shutdown_result(True)

    assert manager.apply_pending_update_and_restart() is False
    assert manager.transaction["phase"] == "preflight_blocked"
    assert manager.transaction["error"] == "pre_shutdown_approval_missing_or_expired"


def test_failed_transaction_restores_verified_staged_asset_for_retry(tmp_path, monkeypatch):
    manager, _target, asset = _windows_update_manager(tmp_path, monkeypatch)
    manager._write_transaction("failed", error="antivirus_locked_target")

    restored = AutoUpdateManager(settings={})

    assert restored.has_pending_update() is True
    assert Path(restored.pending_update["asset_path"]) == asset


def test_post_update_health_requires_installed_sha_even_for_same_version(tmp_path, monkeypatch):
    manager, target, _asset = _windows_update_manager(tmp_path, monkeypatch)
    manager.transaction["phase"] = "postcheck_pending"
    manager.set_safety_callbacks(health_callback=lambda _transaction: {"ok": True})
    monkeypatch.setattr(manager, "schedule_rollback", lambda: False)

    result = manager.complete_post_update_health_check()

    assert result["ok"] is False
    assert result["health"]["reason"] == "installed_sha256_mismatch"


def test_apply_script_sets_postcheck_before_launch_and_verifies_installed_sha():
    script = AutoUpdateManager._build_apply_script(
        target_exe="C:/NoahAI/AITrading.exe",
        new_exe="C:/NoahAI/cache/AITrading.new.exe",
        backup_exe="C:/NoahAI/AITrading.exe.bak",
        journal_path="C:/NoahAI/update.json",
        expected_sha="b" * 64,
        old_version="3.9.0.8",
        new_version="3.9.0.8",
    )

    assert "installed SHA256 mismatch after replacement" in script
    assert script.index("Set-Phase 'postcheck_pending'") < script.index("$proc = Start-Process")
    assert "Set-Phase 'launched'" not in script
