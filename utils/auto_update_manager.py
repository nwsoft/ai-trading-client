#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Automatic update manager for Windows client."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request


class AutoUpdateManager:
    """Manages periodic update checks, downloads, and apply-on-exit flow."""

    DEFAULT_RELEASE_REPOSITORY = "nwsoft/ai-trading-client"
    DEFAULT_REPOSITORIES = [DEFAULT_RELEASE_REPOSITORY]

    def __init__(self, settings: Optional[Dict[str, Any]] = None, logger: Any = None):
        self.logger = logger
        self.settings: Dict[str, Any] = settings or {}
        self.repositories = list(self.DEFAULT_REPOSITORIES)

        self.enabled = True
        self.auto_download = True
        self.auto_apply_on_exit = True
        self.check_interval_hours = 6

        self._ui_root = None
        self._after_job = None
        self._notify_callback: Optional[Callable[[str], None]] = None
        self._apply_started = False

        self.last_check_result: Dict[str, Any] = {}
        self.pending_update: Dict[str, Any] = {}

        self.update_cache_dir = self._resolve_update_cache_dir()
        self.update_cache_dir.mkdir(parents=True, exist_ok=True)

        self.install_target_marker_path = self._resolve_install_target_marker_path()
        self.install_target_exe = self._resolve_install_target_executable()

        self.update_settings(self.settings)

    def update_settings(self, settings: Optional[Dict[str, Any]] = None):
        """Refresh runtime behavior from current settings."""
        if isinstance(settings, dict):
            self.settings = settings

        ui_settings = self.settings.get("ui_settings", {}) if isinstance(self.settings, dict) else {}
        if not isinstance(ui_settings, dict):
            ui_settings = {}

        self.enabled = bool(ui_settings.get("auto_update_enabled", True))
        self.auto_download = bool(ui_settings.get("auto_update_auto_download", True))
        self.auto_apply_on_exit = bool(ui_settings.get("auto_update_auto_apply_on_exit", True))

        try:
            interval = int(ui_settings.get("auto_update_check_interval_hours", 6))
        except Exception:
            interval = 6
        self.check_interval_hours = max(1, min(interval, 72))

        # 단일 릴리즈 저장소를 기본으로 사용하고, 필요 시 설정에서만 오버라이드한다.
        repo_override = str(ui_settings.get("auto_update_release_repo", "") or "").strip()
        if repo_override:
            self.repositories = [repo_override]
        else:
            self.repositories = list(self.DEFAULT_REPOSITORIES)

    def start_scheduler(self, ui_root: Any, notify_callback: Optional[Callable[[str], None]] = None):
        """Start periodic background checks bound to Tk root."""
        self.stop_scheduler()
        self._ui_root = ui_root
        self._notify_callback = notify_callback

        if not self.enabled or self._ui_root is None:
            return

        initial_delay_ms = 60 * 1000
        self._after_job = self._ui_root.after(initial_delay_ms, self._scheduled_check)
        self._log_info(f"auto-update scheduler started (interval={self.check_interval_hours}h)")

    def stop_scheduler(self):
        """Stop periodic checks."""
        if self._ui_root is not None and self._after_job is not None:
            try:
                self._ui_root.after_cancel(self._after_job)
            except Exception:
                pass
        self._after_job = None

    def check_for_updates(self, manual: bool = False) -> Dict[str, Any]:
        """Check latest release and optionally pre-download update executable."""
        now = datetime.now(timezone.utc).isoformat()
        result: Dict[str, Any] = {
            "ok": False,
            "checked_at": now,
            "update_available": False,
            "downloaded": False,
            "reason": "",
        }

        release = self._fetch_latest_release()
        if not release:
            result["reason"] = "latest_release_unavailable"
            self.last_check_result = result
            return result

        current_version = self._get_current_version()
        latest_version = str(release.get("tag_name") or "").strip()
        if not latest_version:
            result["reason"] = "latest_version_missing"
            self.last_check_result = result
            return result

        update_available = self._normalize_version(latest_version) > self._normalize_version(current_version)

        result.update({
            "ok": True,
            "current_version": current_version,
            "latest_version": latest_version,
            "release_url": release.get("html_url", ""),
            "repo": release.get("_repo", ""),
            "update_available": update_available,
        })

        if not update_available:
            self.last_check_result = result
            return result

        self.pending_update = {
            "latest_version": latest_version,
            "release_url": release.get("html_url", ""),
            "repo": release.get("_repo", ""),
            "asset_path": "",
            "downloaded": False,
        }

        if self.auto_download or manual:
            dl = self.download_latest_update(release_payload=release)
            result["downloaded"] = bool(dl.get("ok"))
            if dl.get("ok"):
                self.pending_update.update(
                    {
                        "asset_path": dl.get("asset_path", ""),
                        "downloaded": True,
                        "sha256": dl.get("sha256", ""),
                    }
                )
            else:
                result["download_error"] = dl.get("reason", "download_failed")

        self.last_check_result = result
        return result

    def download_latest_update(self, release_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Download latest AITrading.exe from release assets and verify checksum when available."""
        release = release_payload or self._fetch_latest_release()
        if not release:
            return {"ok": False, "reason": "latest_release_unavailable"}

        assets = release.get("assets", [])
        if not isinstance(assets, list):
            return {"ok": False, "reason": "assets_unavailable"}

        exe_asset = None
        for asset in assets:
            name = str(asset.get("name") or "")
            if name.lower() == "aitrading.exe":
                exe_asset = asset
                break
        if exe_asset is None:
            for asset in assets:
                name = str(asset.get("name") or "").lower()
                if name.endswith(".exe"):
                    exe_asset = asset
                    break
        if exe_asset is None:
            return {"ok": False, "reason": "exe_asset_not_found"}

        version = str(release.get("tag_name") or "").strip().lstrip("v")
        target_dir = self.update_cache_dir / version
        target_dir.mkdir(parents=True, exist_ok=True)

        exe_name = str(exe_asset.get("name") or "AITrading.exe")
        exe_url = str(exe_asset.get("browser_download_url") or "").strip()
        if not exe_url:
            return {"ok": False, "reason": "exe_url_missing"}

        staged_name = exe_name
        if exe_name.lower() == "aitrading.exe":
            # 캐시에 실제 런처 이름이 그대로 보이면 사용자가 설치 경로로 오해하기 쉽다.
            staged_name = "AITrading.new.exe"

        target_path = target_dir / staged_name
        tmp_path = target_dir / f"{staged_name}.download"

        ok = self._download_file(exe_url, tmp_path)
        if not ok:
            return {"ok": False, "reason": "download_failed"}

        expected_sha = self._fetch_expected_sha_from_manifest(assets)
        actual_sha = self._sha256_file(tmp_path)

        if expected_sha and expected_sha != actual_sha:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return {"ok": False, "reason": "sha256_mismatch", "expected_sha": expected_sha, "actual_sha": actual_sha}

        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        tmp_path.rename(target_path)

        return {
            "ok": True,
            "asset_path": str(target_path),
            "sha256": actual_sha,
            "expected_sha": expected_sha,
            "version": version,
        }

    def apply_pending_update_and_restart(self) -> bool:
        """Apply downloaded update via external PowerShell script and relaunch app."""
        if self._apply_started:
            return False
        if not self.auto_apply_on_exit:
            return False
        if not self.pending_update or not self.pending_update.get("downloaded"):
            return False
        if not sys.platform.startswith("win"):
            return False
        if not getattr(sys, "frozen", False):
            self._log_info("auto-apply skipped in non-frozen runtime")
            return False

        asset_path = Path(str(self.pending_update.get("asset_path") or ""))
        if not asset_path.exists():
            return False

        target_exe = self._resolve_install_target_executable()
        self.install_target_exe = target_exe

        if self._is_path_under(target_exe, self.update_cache_dir):
            self._log_warning(
                f"update target resolved to cache path and was rejected: {target_exe}"
            )
            return False

        if not target_exe.exists():
            return False

        script_path = self.update_cache_dir / f"apply_update_{self.pending_update.get('latest_version', 'latest')}.ps1"
        backup_path = target_exe.with_suffix(target_exe.suffix + ".bak")

        script = self._build_apply_script(
            target_exe=str(target_exe),
            new_exe=str(asset_path),
            backup_exe=str(backup_path),
        )
        script_path.write_text(script, encoding="utf-8")

        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        try:
            subprocess.Popen(
                [
                    "powershell",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-WindowStyle",
                    "Hidden",
                    "-File",
                    str(script_path),
                ],
                creationflags=flags,
                close_fds=True,
            )
            self._apply_started = True
            self._log_info(f"auto-update apply scheduled: {asset_path}")
            return True
        except Exception as exc:
            self._log_warning(f"failed to spawn apply script: {exc}")
            return False

    def has_pending_update(self) -> bool:
        return bool(self.pending_update.get("downloaded"))

    def get_runtime_diagnostics(self) -> Dict[str, str]:
        current_exe = str(Path(sys.executable))
        install_target = str(self.install_target_exe or Path(sys.executable))
        pending_asset = str(self.pending_update.get("asset_path") or "")
        return {
            "current_exe": current_exe,
            "install_target_exe": install_target,
            "update_cache_dir": str(self.update_cache_dir),
            "pending_asset_path": pending_asset,
        }

    def _scheduled_check(self):
        try:
            res = self.check_for_updates(manual=False)
            if res.get("update_available"):
                latest = res.get("latest_version", "")
                downloaded = bool(res.get("downloaded"))
                if downloaded:
                    self._notify(f"새 버전 {latest} 다운로드 완료. 앱 종료 시 자동 업데이트됩니다.")
                else:
                    self._notify(f"새 버전 {latest} 감지됨. 업데이트 탭에서 확인하세요.")
        except Exception as exc:
            self._log_warning(f"scheduled update check failed: {exc}")
        finally:
            if self.enabled and self._ui_root is not None:
                interval_ms = self.check_interval_hours * 60 * 60 * 1000
                self._after_job = self._ui_root.after(interval_ms, self._scheduled_check)

    def _fetch_latest_release(self) -> Optional[Dict[str, Any]]:
        headers = {
            "User-Agent": "NoahAI-AutoUpdate/1.0",
            "Accept": "application/vnd.github+json",
        }
        for repo in self.repositories:
            url = f"https://api.github.com/repos/{repo}/releases/latest"
            req = urllib_request.Request(url, headers=headers)
            try:
                with urllib_request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode("utf-8", errors="ignore")
                payload = json.loads(body)
                if isinstance(payload, dict) and payload.get("tag_name"):
                    payload["_repo"] = repo
                    return payload
            except urllib_error.HTTPError:
                continue
            except urllib_error.URLError:
                continue
            except Exception:
                continue
        return None

    def _fetch_expected_sha_from_manifest(self, assets: Any) -> str:
        try:
            manifest_asset = None
            for asset in assets:
                name = str(asset.get("name") or "").lower()
                if name == "release-manifest.json":
                    manifest_asset = asset
                    break
            if not manifest_asset:
                return ""

            manifest_url = str(manifest_asset.get("browser_download_url") or "").strip()
            if not manifest_url:
                return ""

            req = urllib_request.Request(
                manifest_url,
                headers={"User-Agent": "NoahAI-AutoUpdate/1.0"},
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(body)
            exe_sha = (
                data.get("assets", {})
                .get("exe", {})
                .get("sha256", "")
            )
            return str(exe_sha or "").strip().lower()
        except Exception:
            return ""

    def _download_file(self, url: str, output_path: Path) -> bool:
        try:
            req = urllib_request.Request(url, headers={"User-Agent": "NoahAI-AutoUpdate/1.0"})
            with urllib_request.urlopen(req, timeout=30) as resp, output_path.open("wb") as f:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
            return True
        except Exception as exc:
            self._log_warning(f"download failed ({url}): {exc}")
            return False

    def _resolve_update_cache_dir(self) -> Path:
        try:
            from path_utils import get_cache_dir

            return Path(get_cache_dir()) / "auto_updater"
        except Exception:
            return Path(os.getcwd()) / "data" / "cache" / "auto_updater"

    def _resolve_install_target_marker_path(self) -> Path:
        try:
            from path_utils import get_app_data_dir

            config_dir = Path(get_app_data_dir()) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "auto_update_target.json"
        except Exception:
            return self.update_cache_dir / "auto_update_target.json"

    @staticmethod
    def _is_path_under(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    def _read_persisted_install_target(self) -> Optional[Path]:
        try:
            if not self.install_target_marker_path.exists():
                return None
            payload = json.loads(self.install_target_marker_path.read_text(encoding="utf-8"))
            value = str(payload.get("install_target_exe") or "").strip()
            if not value:
                return None
            return Path(value)
        except Exception:
            return None

    def _persist_install_target(self, target_path: Path):
        try:
            payload = {
                "install_target_exe": str(target_path),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self.install_target_marker_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _resolve_install_target_executable(self) -> Path:
        current_exe = Path(sys.executable)
        if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
            return current_exe

        persisted = self._read_persisted_install_target()

        # 정상 경로에서 실행 중이면 그 경로를 설치 타겟으로 고정한다.
        if not self._is_path_under(current_exe, self.update_cache_dir):
            self._persist_install_target(current_exe)
            return current_exe

        # 캐시에서 실행된 경우에는 이전에 저장한 정상 타겟이 있으면 우선한다.
        if persisted and persisted.exists() and not self._is_path_under(persisted, self.update_cache_dir):
            self._log_info(
                f"current executable is in update cache; using persisted install target: {persisted}"
            )
            return persisted

        self._log_warning(
            "current executable is in update cache and no persisted install target exists; "
            f"falling back to current executable: {current_exe}"
        )
        return current_exe

    @staticmethod
    def _normalize_version(version_text: str) -> tuple:
        cleaned = str(version_text or "").strip().lower().lstrip("v")
        nums = re.findall(r"\d+", cleaned)
        return tuple(int(x) for x in nums)

    @staticmethod
    def _sha256_file(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _build_apply_script(target_exe: str, new_exe: str, backup_exe: str) -> str:
        target = target_exe.replace("'", "''")
        new = new_exe.replace("'", "''")
        backup = backup_exe.replace("'", "''")
        return f"""
$ErrorActionPreference = 'Stop'
$target = '{target}'
$newExe = '{new}'
$backup = '{backup}'

function Restore-And-Start {{
    if (Test-Path $backup) {{
        Copy-Item -Path $backup -Destination $target -Force
    }}
    if (Test-Path $target) {{
        Start-Process -FilePath $target | Out-Null
    }}
}}

Start-Sleep -Seconds 1

if (-not (Test-Path $newExe)) {{
    Restore-And-Start
    exit 1
}}

if (Test-Path $target) {{
    try {{
        Copy-Item -Path $target -Destination $backup -Force
    }} catch {{
        # 백업 실패는 치명적이지 않을 수 있으므로 복사 재시도 로직으로 진행
    }}
}}

$copied = $false
for ($i = 0; $i -lt 60; $i++) {{
    try {{
        Copy-Item -Path $newExe -Destination $target -Force
        $copied = $true
        break
    }} catch {{
        Start-Sleep -Seconds 1
    }}
}}

if (-not $copied) {{
    Restore-And-Start
    exit 1
}}

try {{
    $proc = Start-Process -FilePath $target -PassThru
    Start-Sleep -Seconds 8
    Get-Process -Id $proc.Id -ErrorAction Stop | Out-Null
    exit 0
}} catch {{
    Restore-And-Start
    exit 1
}}
""".strip() + "\n"

    def _get_current_version(self) -> str:
        try:
            from config.app_version import RELEASE_VERSION

            return str(RELEASE_VERSION).strip()
        except Exception:
            return "0.0.0"

    def _notify(self, message: str):
        if callable(self._notify_callback):
            try:
                self._notify_callback(message)
                return
            except Exception:
                pass
        self._log_info(message)

    def _log_info(self, message: str):
        try:
            if self.logger and hasattr(self.logger, "info"):
                self.logger.info(message)
        except Exception:
            pass

    def _log_warning(self, message: str):
        try:
            if self.logger and hasattr(self.logger, "warning"):
                self.logger.warning(message)
        except Exception:
            pass
