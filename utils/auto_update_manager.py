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
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse


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
        self._progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._preflight_callback: Optional[Callable[[str], Dict[str, Any]]] = None
        self._health_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
        self._apply_started = False
        self._shutdown_confirmed = False
        self._approved_preflight: Dict[str, Any] = {}
        self._check_running = False
        self._sha_cache: Dict[str, Any] = {}

        self.last_check_result: Dict[str, Any] = {}
        self.pending_update: Dict[str, Any] = {}

        self.update_cache_dir = self._resolve_update_cache_dir()
        self.update_cache_dir.mkdir(parents=True, exist_ok=True)

        self.install_target_marker_path = self._resolve_install_target_marker_path()
        self.transaction_journal_path = self._resolve_transaction_journal_path()
        self.install_target_exe = self._resolve_install_target_executable()
        self.transaction: Dict[str, Any] = self._read_transaction()
        self._restore_pending_update()
        self._prune_update_cache(keep_latest_versions=2)

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
        self.open_position_action = str(
            ui_settings.get("auto_update_open_position_action", "defer") or "defer"
        ).strip().lower()
        if self.open_position_action not in {"defer", "keep_with_tp_sl", "close_all"}:
            self.open_position_action = "defer"

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

        # 사용자가 앱을 짧게 실행해도 새 버전을 확인할 수 있도록 초기 검사를
        # 빠르게 시작한다. 네트워크 조회는 _scheduled_check의 백그라운드
        # 스레드에서 수행하므로 UI를 막지 않는다.
        # 초기 렌더링·거래소 연결과 디스크/네트워크 경쟁하지 않도록 15초 뒤
        # 한 번 확인한다. 이후 주기는 사용자가 설정한 1~72시간 값이다.
        initial_delay_ms = 15 * 1000
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

    def set_progress_callback(self, callback: Optional[Callable[[Dict[str, Any]], None]] = None):
        """UI에서 다운로드 진행률/완료 이벤트를 받을 콜백을 등록한다."""
        self._progress_callback = callback

    def set_safety_callbacks(
        self,
        *,
        preflight_callback: Optional[Callable[[str], Dict[str, Any]]] = None,
        health_callback: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> None:
        self._preflight_callback = preflight_callback
        self._health_callback = health_callback

    def record_shutdown_result(self, ok: bool) -> None:
        self._shutdown_confirmed = bool(ok)
        if not ok and self.has_pending_update():
            self._write_transaction("shutdown_failed", error="거래 정지 또는 DB/log flush 실패")

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

        latest_tuple = self._normalize_version(latest_version)
        current_tuple = self._normalize_version(current_version)
        update_available = latest_tuple > current_tuple
        update_reason = "newer_version" if update_available else ""
        installed_sha = ""
        release_sha = ""

        # Fix Patch는 제품 버전 문자열을 유지한 채 같은 GitHub release의
        # SHA 검증 EXE를 교체할 수 있다. 버전만 비교하면 3.9.0.4 Fix Patch 1
        # 사용자가 같은 3.9.0.4 Fix Patch 2를 영원히 감지하지 못하므로,
        # frozen Windows 설치본에서는 manifest SHA까지 비교한다.
        if latest_tuple == current_tuple:
            verification = self._fetch_verification_policy_from_manifest(release.get("assets", []))
            release_sha = str(verification.get("sha256") or "")
            if (
                sys.platform.startswith("win")
                and getattr(sys, "frozen", False)
                and not release_sha
            ):
                result["reason"] = "release_manifest_or_sha256_missing"
                self.last_check_result = result
                return result
            installed_sha = self._installed_executable_sha()
            if release_sha and installed_sha and release_sha != installed_sha:
                update_available = True
                update_reason = "same_version_asset_changed"

        result.update({
            "ok": True,
            "current_version": current_version,
            "latest_version": latest_version,
            "release_url": release.get("html_url", ""),
            "repo": release.get("_repo", ""),
            "update_available": update_available,
            "update_reason": update_reason,
        })
        if installed_sha:
            result["installed_sha256"] = installed_sha
        if release_sha:
            result["release_sha256"] = release_sha

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
                        "verification": dict(dl.get("verification") or {}),
                    }
                )
                self._write_transaction(
                    "downloaded",
                    old_version=current_version,
                    new_version=latest_version,
                    sha256=dl.get("sha256", ""),
                    asset_path=dl.get("asset_path", ""),
                    target_path=str(self.install_target_exe),
                    release_url=release.get("html_url", ""),
                    verification=dict(dl.get("verification") or {}),
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
        if not self._is_trusted_github_https_url(exe_url):
            return {"ok": False, "reason": "untrusted_release_url"}

        staged_name = exe_name
        if exe_name.lower() == "aitrading.exe":
            # 캐시에 실제 런처 이름이 그대로 보이면 사용자가 설치 경로로 오해하기 쉽다.
            staged_name = "AITrading.new.exe"

        target_path = target_dir / staged_name
        tmp_path = target_dir / f"{staged_name}.download"

        self._emit_progress(
            event="download_start",
            version=version,
            file_name=staged_name,
            target_path=str(target_path),
            cache_dir=str(self.update_cache_dir),
            install_target=str(self.install_target_exe),
        )

        ok = self._download_file(exe_url, tmp_path)
        if not ok:
            self._emit_progress(event="download_failed", reason="download_failed")
            return {"ok": False, "reason": "download_failed"}

        verification = self._fetch_verification_policy_from_manifest(assets)
        expected_sha = str(verification.get("sha256") or "")
        actual_sha = self._sha256_file(tmp_path)

        if not expected_sha:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._emit_progress(event="download_failed", reason="release_manifest_or_sha256_missing")
            return {"ok": False, "reason": "release_manifest_or_sha256_missing"}

        if expected_sha != actual_sha:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            self._emit_progress(
                event="download_failed",
                reason="sha256_mismatch",
                expected_sha=expected_sha,
                actual_sha=actual_sha,
            )
            return {"ok": False, "reason": "sha256_mismatch", "expected_sha": expected_sha, "actual_sha": actual_sha}

        if target_path.exists():
            try:
                target_path.unlink()
            except Exception:
                pass
        tmp_path.rename(target_path)

        # 오래된 버전 캐시/스크립트는 정리해 누적 오염을 방지한다.
        self._prune_update_cache(keep_latest_versions=2)

        self._emit_progress(
            event="download_completed",
            version=version,
            asset_path=str(target_path),
            cache_dir=str(self.update_cache_dir),
            install_target=str(self.install_target_exe),
            sha256=actual_sha,
        )

        return {
            "ok": True,
            "asset_path": str(target_path),
            "sha256": actual_sha,
            "expected_sha": expected_sha,
            "verification": verification,
            "version": version,
        }

    def authorize_pending_update(self) -> Dict[str, Any]:
        """Approve one exact staged asset *before* trading adapters are stopped.

        The approval is intentionally bound to the staged path, SHA and install
        target.  Shutdown is performed only after this method succeeds; apply
        then consumes the approval without querying already-stopped adapters.
        """
        if not self.auto_apply_on_exit or not self.has_pending_update():
            return {"ok": True, "needed": False}

        asset_path = Path(str(self.pending_update.get("asset_path") or ""))
        expected_sha = str(
            self.pending_update.get("sha256") or self.transaction.get("sha256") or ""
        ).lower()
        if not asset_path.is_file():
            result = {"ok": False, "needed": True, "reason": "staged_executable_missing"}
            self._write_transaction("verification_failed", error=result["reason"])
            return result
        actual_sha = self._sha256_file(asset_path)
        if not expected_sha or actual_sha != expected_sha:
            result = {
                "ok": False,
                "needed": True,
                "reason": "staged_sha256_invalid",
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
            }
            self._write_transaction("verification_failed", error=result["reason"])
            return result

        target_exe = self._resolve_install_target_executable()
        self.install_target_exe = target_exe
        target_check = self._check_install_target_replaceable(target_exe)
        if not target_check.get("ok"):
            result = {"ok": False, "needed": True, **target_check}
            self._write_transaction(
                "target_not_writable",
                error=str(result.get("reason") or "target_not_writable"),
                target_path=str(target_exe),
            )
            return result

        existing = dict(self._approved_preflight or {})
        existing_age = time.time() - float(existing.get("approved_at_epoch") or 0)
        if (
            existing.get("ok")
            and 0 <= existing_age <= 120
            and str(existing.get("asset_path") or "") == str(asset_path)
            and str(existing.get("sha256") or "").lower() == expected_sha
            and str(existing.get("target_path") or "") == str(target_exe)
        ):
            return existing

        preflight = self.run_update_preflight()
        if not preflight.get("ok"):
            self._write_transaction(
                "preflight_blocked",
                error=str(preflight.get("reason") or "trading_state_unsafe"),
                preflight=preflight,
            )
            return {"ok": False, "needed": True, **preflight}

        approval = {
            "ok": True,
            "needed": True,
            "approved_at_epoch": time.time(),
            "asset_path": str(asset_path),
            "sha256": expected_sha,
            "target_path": str(target_exe),
            "preflight": preflight,
        }
        self._approved_preflight = dict(approval)
        self._write_transaction(
            "preflight_approved",
            asset_path=str(asset_path),
            target_path=str(target_exe),
            sha256=expected_sha,
            preflight=preflight,
            preflight_approved_at=datetime.now(timezone.utc).isoformat(),
        )
        return approval

    def apply_pending_update_and_restart(self) -> bool:
        """Apply downloaded update via external PowerShell script and relaunch app."""
        if self._apply_started:
            return False
        if not self.auto_apply_on_exit:
            return False
        if not self.pending_update or not self.pending_update.get("downloaded"):
            return False
        if not self._shutdown_confirmed:
            self._write_transaction("shutdown_not_confirmed", error="안전 종료 확인 전에는 업데이트를 적용할 수 없습니다.")
            return False
        if not sys.platform.startswith("win"):
            return False
        if not getattr(sys, "frozen", False):
            self._log_info("auto-apply skipped in non-frozen runtime")
            return False

        asset_path = Path(str(self.pending_update.get("asset_path") or ""))
        if not asset_path.exists():
            return False

        expected_sha = str(self.pending_update.get("sha256") or self.transaction.get("sha256") or "").lower()
        if not expected_sha or self._sha256_file(asset_path) != expected_sha:
            self._write_transaction("verification_failed", error="staged_sha256_invalid")
            return False
        approval = dict(self._approved_preflight or {})
        approval_age = time.time() - float(approval.get("approved_at_epoch") or 0)
        approval_matches = bool(
            approval.get("ok")
            and 0 <= approval_age <= 120
            and str(approval.get("asset_path") or "") == str(asset_path)
            and str(approval.get("sha256") or "").lower() == expected_sha
        )
        if not approval_matches:
            self._write_transaction(
                "preflight_blocked",
                error="pre_shutdown_approval_missing_or_expired",
            )
            return False

        preflight = dict(approval.get("preflight") or {})
        target_exe = Path(str(approval.get("target_path") or ""))
        self.install_target_exe = target_exe

        if self._looks_like_update_cache_path(target_exe):
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
            journal_path=str(self.transaction_journal_path),
            expected_sha=expected_sha,
            old_version=str(self.transaction.get("old_version") or self._get_current_version()),
            new_version=str(self.pending_update.get("latest_version") or self.transaction.get("new_version") or ""),
        )
        script_path.write_text(script, encoding="utf-8")
        self._write_transaction(
            "apply_scheduled",
            old_version=str(self.transaction.get("old_version") or self._get_current_version()),
            new_version=str(self.pending_update.get("latest_version") or self.transaction.get("new_version") or ""),
            sha256=expected_sha,
            asset_path=str(asset_path),
            target_path=str(target_exe),
            backup_path=str(backup_path),
            preflight=preflight,
            verification=dict(
                self.pending_update.get("verification")
                or self.transaction.get("verification")
                or {}
            ),
            awaiting_user_resume=True,
        )

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
            self._approved_preflight = {}
            self._log_info(f"auto-update apply scheduled: {asset_path}")
            return True
        except Exception as exc:
            self._write_transaction("apply_spawn_failed", error=str(exc))
            self._log_warning(f"failed to spawn apply script: {exc}")
            return False

    def run_update_preflight(self) -> Dict[str, Any]:
        if not callable(self._preflight_callback):
            return {"ok": False, "reason": "preflight_callback_missing"}
        try:
            result = self._preflight_callback(self.open_position_action)
            return dict(result or {"ok": False, "reason": "preflight_empty"})
        except Exception as exc:
            return {"ok": False, "reason": "preflight_exception", "error": str(exc)}

    def has_pending_update(self) -> bool:
        return bool(self.pending_update.get("downloaded"))

    def get_runtime_diagnostics(self) -> Dict[str, str]:
        current_exe = str(Path(sys.executable))
        install_target = str(self.install_target_exe or Path(sys.executable))
        pending_asset = str(self.pending_update.get("asset_path") or "")
        installed_sha = self._installed_executable_sha()
        expected_sha = str(
            self.pending_update.get("sha256") or self.transaction.get("sha256") or ""
        ).lower()
        return {
            "current_exe": current_exe,
            "install_target_exe": install_target,
            "update_cache_dir": str(self.update_cache_dir),
            "pending_asset_path": pending_asset,
            "transaction_phase": str(self.transaction.get("phase") or "none"),
            "transaction_error": str(
                self.transaction.get("error") or self.transaction.get("detail") or ""
            ),
            "transaction_journal": str(self.transaction_journal_path),
            "installed_sha256": installed_sha,
            "expected_sha256": expected_sha,
            "asset_matches_installed": str(bool(installed_sha and expected_sha and installed_sha == expected_sha)).lower(),
        }

    def needs_post_update_health_check(self) -> bool:
        return str(self.transaction.get("phase") or "") in {
            "launched", "postcheck_pending", "apply_scheduled", "replacing"
        }

    def is_trading_locked(self) -> bool:
        phase = str(self.transaction.get("phase") or "")
        return bool(
            self.transaction.get("awaiting_user_resume")
            or phase in {"apply_scheduled", "replacing", "launched", "postcheck_pending", "rollback_scheduled", "health_failed"}
        )

    def acknowledge_user_resume(self) -> bool:
        if self.needs_post_update_health_check():
            return False
        self._write_transaction(
            str(self.transaction.get("phase") or "healthy"),
            awaiting_user_resume=False,
            resumed_at=datetime.now(timezone.utc).isoformat(),
        )
        return True

    def complete_post_update_health_check(self) -> Dict[str, Any]:
        if not self.needs_post_update_health_check():
            return {"ok": True, "needed": False, "transaction": dict(self.transaction)}
        if not callable(self._health_callback):
            result = {"ok": False, "reason": "health_callback_missing"}
        else:
            try:
                result = dict(self._health_callback(dict(self.transaction)) or {})
            except Exception as exc:
                result = {"ok": False, "reason": "health_check_exception", "error": str(exc)}
        expected = self._normalize_version(str(self.transaction.get("new_version") or ""))
        actual = self._normalize_version(self._get_current_version())
        if expected and actual != expected:
            result = {
                "ok": False,
                "reason": "version_mismatch",
                "expected_version": self.transaction.get("new_version"),
                "actual_version": self._get_current_version(),
                "details": result,
            }
        expected_sha = str(self.transaction.get("sha256") or "").lower()
        target_path = Path(str(self.transaction.get("target_path") or sys.executable))
        try:
            actual_sha = self._sha256_file(target_path) if target_path.is_file() else ""
        except Exception:
            actual_sha = ""
        if not expected_sha or actual_sha != expected_sha:
            result = {
                "ok": False,
                "reason": "installed_sha256_mismatch",
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "details": result,
            }
        if result.get("ok"):
            old_version = str(self.transaction.get("old_version") or "")
            new_version = str(self.transaction.get("new_version") or self._get_current_version())
            self._write_transaction(
                "healthy",
                health=result,
                completed_at=datetime.now(timezone.utc).isoformat(),
                awaiting_user_resume=True,
            )
            return {
                "ok": True,
                "needed": True,
                "message": f"v{old_version} → v{new_version} 업데이트가 완료되었습니다.",
                "awaiting_user_resume": True,
            }
        self._write_transaction(
            "health_failed",
            health=result,
            awaiting_user_resume=True,
        )
        rollback = self.schedule_rollback()
        return {"ok": False, "needed": True, "health": result, "rollback_scheduled": rollback}

    def schedule_rollback(self) -> bool:
        if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
            return False
        target = Path(str(self.transaction.get("target_path") or ""))
        backup = Path(str(self.transaction.get("backup_path") or ""))
        if not target or not backup.exists() or self._looks_like_update_cache_path(target):
            return False
        script_path = self.update_cache_dir / "rollback_failed_update.ps1"
        target_q = str(target).replace("'", "''")
        backup_q = str(backup).replace("'", "''")
        journal_q = str(self.transaction_journal_path).replace("'", "''")
        script_path.write_text(
            f"""$ErrorActionPreference = 'Stop'
$target = '{target_q}'
$backup = '{backup_q}'
$journal = '{journal_q}'
Start-Sleep -Seconds 2
for ($i = 0; $i -lt 60; $i++) {{
    try {{
        Copy-Item -Path $backup -Destination $target -Force
        $state = Get-Content -Raw -Path $journal | ConvertFrom-Json
        $state.phase = 'rolled_back'
        $state.rolled_back_at = (Get-Date).ToUniversalTime().ToString('o')
        $state | ConvertTo-Json -Depth 10 | Set-Content -Path $journal -Encoding UTF8
        Start-Process -FilePath $target | Out-Null
        exit 0
    }} catch {{
        Start-Sleep -Seconds 1
    }}
}}
exit 1
""",
            encoding="utf-8",
        )
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script_path)],
                creationflags=flags,
                close_fds=True,
            )
            self._write_transaction("rollback_scheduled", awaiting_user_resume=True)
            return True
        except Exception:
            return False

    def _scheduled_check(self):
        if not self.enabled or self._ui_root is None:
            return

        # 다음 검사는 UI 스레드에서 먼저 예약하고, 이번 네트워크 요청만 별도
        # 스레드로 보낸다. 동일 검사가 겹치는 것도 차단한다.
        interval_ms = self.check_interval_hours * 60 * 60 * 1000
        self._after_job = self._ui_root.after(interval_ms, self._scheduled_check)
        if self._check_running:
            return
        self._check_running = True

        def _worker():
            def _notify_on_ui(message: str) -> None:
                root = self._ui_root
                dispatcher = getattr(root, "thread_safe_after", None) if root is not None else None
                if callable(dispatcher):
                    dispatcher(0, self._notify, message)
                else:
                    self._notify(message)

            try:
                res = self.check_for_updates(manual=False)
                if res.get("update_available"):
                    latest = res.get("latest_version", "")
                    downloaded = bool(res.get("downloaded"))
                    if downloaded:
                        _notify_on_ui(f"새 버전 {latest} 다운로드 완료. 앱 종료 시 자동 업데이트됩니다.")
                    else:
                        reason = str(res.get("download_error") or "다운로드 대기")
                        _notify_on_ui(f"새 버전 {latest} 감지됨. 자동 다운로드 실패/대기: {reason}")
                elif not res.get("ok"):
                    self._log_warning(
                        f"scheduled update check unavailable: {res.get('reason', 'unknown')}"
                    )
            except Exception as exc:
                self._log_warning(f"scheduled update check failed: {exc}")
            finally:
                self._check_running = False

        threading.Thread(
            target=_worker,
            name="NoahAIAutoUpdateCheck",
            daemon=True,
        ).start()

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

    def _fetch_verification_policy_from_manifest(self, assets: Any) -> Dict[str, Any]:
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
            if not self._is_trusted_github_https_url(manifest_url):
                return {}

            req = urllib_request.Request(
                manifest_url,
                headers={"User-Agent": "NoahAI-AutoUpdate/1.0"},
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="ignore")
            data = json.loads(body)
            verification = data.get("verification", {})
            if not isinstance(verification, dict):
                return {}
            exe_sha = (
                data.get("assets", {})
                .get("exe", {})
                .get("sha256", "")
            )
            normalized = str(exe_sha or "").strip().lower()
            if (
                verification.get("sha256_required") is not True
                or verification.get("authenticode_required") is not False
                or not re.fullmatch(r"[0-9a-f]{64}", normalized)
            ):
                return {}
            return {
                "sha256": normalized,
                "sha256_required": True,
                "authenticode_required": False,
                "source": str(verification.get("source") or "github_release_manifest"),
                "manifest_url": manifest_url,
            }
        except Exception:
            return {}

    def _fetch_expected_sha_from_manifest(self, assets: Any) -> str:
        """이전 호출부 호환용. 실제 정책 검증은 manifest 전체를 사용한다."""
        return str(self._fetch_verification_policy_from_manifest(assets).get("sha256") or "")

    @staticmethod
    def _is_trusted_github_https_url(url: str) -> bool:
        try:
            parsed = urlparse(str(url or "").strip())
            host = str(parsed.hostname or "").lower()
            return bool(
                parsed.scheme == "https"
                and (
                    host == "github.com"
                    or host.endswith(".github.com")
                    or host == "githubusercontent.com"
                    or host.endswith(".githubusercontent.com")
                )
            )
        except Exception:
            return False

    def _installed_executable_sha(self) -> str:
        """Return the stable installed EXE SHA for same-version patch checks."""
        if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
            return ""
        try:
            target = self._resolve_install_target_executable()
            if not target.exists() or target.suffix.lower() != ".exe":
                return ""
            stat = target.stat()
            cache_key = str(target.resolve())
            fingerprint = (int(stat.st_size), int(stat.st_mtime_ns))
            cached = self._sha_cache.get(cache_key)
            if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == fingerprint:
                return str(cached[1])
            digest = self._sha256_file(target)
            self._sha_cache[cache_key] = (fingerprint, digest)
            return digest
        except Exception:
            return ""

    def _download_file(self, url: str, output_path: Path) -> bool:
        try:
            req = urllib_request.Request(url, headers={"User-Agent": "NoahAI-AutoUpdate/1.0"})
            with urllib_request.urlopen(req, timeout=30) as resp, output_path.open("wb") as f:
                total_size = 0
                try:
                    total_size = int(resp.headers.get("Content-Length", "0") or "0")
                except Exception:
                    total_size = 0

                received = 0
                last_emitted_percent = -1
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)

                    received += len(chunk)
                    if total_size > 0:
                        percent = int((received / total_size) * 100)
                        if percent != last_emitted_percent:
                            last_emitted_percent = percent
                            self._emit_progress(
                                event="download_progress",
                                percent=percent,
                                downloaded_bytes=received,
                                total_bytes=total_size,
                            )
                    else:
                        # Content-Length를 모를 때도 수신량은 보여준다.
                        self._emit_progress(
                            event="download_progress",
                            percent=None,
                            downloaded_bytes=received,
                            total_bytes=0,
                        )
            return True
        except Exception as exc:
            self._log_warning(f"download failed ({url}): {exc}")
            return False

    def _resolve_update_cache_dir(self) -> Path:
        # Windows 배포본에서는 설치 위치를 우선해 캐시를 잡아
        # "내문서 고정 생성" 체감을 줄이고 설치 위치 중심 동작을 보장한다.
        if sys.platform.startswith("win") and getattr(sys, "frozen", False):
            current_exe = Path(sys.executable)
            exe_parent = current_exe.parent

            install_near_candidates = [
                exe_parent / "cache" / "auto_updater",
                exe_parent / ".auto_updater",
            ]

            local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
            if local_appdata:
                install_near_candidates.append(Path(local_appdata) / "NoahAI" / "cache" / "auto_updater")

            # TEMP는 최후 폴백
            install_near_candidates.append(Path(tempfile.gettempdir()) / "NoahAI" / "cache" / "auto_updater")

            for candidate in install_near_candidates:
                # 이미 auto_updater 캐시 하위에서 실행 중인 경우는 스킵
                lowered = str(candidate).replace("\\", "/").lower()
                if "/auto_updater/" in lowered and str(current_exe).replace("\\", "/").lower().find("/auto_updater/") >= 0:
                    continue
                if self._can_use_cache_dir(candidate):
                    return candidate

        try:
            from path_utils import get_cache_dir

            fallback = Path(get_cache_dir()) / "auto_updater"
            if self._can_use_cache_dir(fallback):
                return fallback
        except Exception:
            pass

        return Path(os.getcwd()) / "data" / "cache" / "auto_updater"

    @staticmethod
    def _can_use_cache_dir(path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _prune_update_cache(self, keep_latest_versions: int = 2):
        try:
            if keep_latest_versions < 1:
                keep_latest_versions = 1

            version_dirs = [p for p in self.update_cache_dir.iterdir() if p.is_dir()]
            version_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            keep_dirs = set(version_dirs[:keep_latest_versions])
            for old_dir in version_dirs[keep_latest_versions:]:
                self._safe_remove_tree(old_dir)

            # 남은 버전 디렉토리명 기준으로 스크립트도 정리
            keep_names = {d.name for d in keep_dirs}
            for script in self.update_cache_dir.glob("apply_update_*.ps1"):
                script_name = script.stem  # apply_update_v3.8.9.26
                version_hint = script_name.replace("apply_update_", "").lstrip("v")
                if version_hint not in keep_names:
                    try:
                        script.unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception:
            # 정리 실패는 업데이트 본 흐름을 막지 않는다.
            pass

    @staticmethod
    def _safe_remove_tree(path: Path):
        try:
            for child in path.rglob("*"):
                if child.is_file() or child.is_symlink():
                    try:
                        child.unlink(missing_ok=True)
                    except Exception:
                        pass
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_dir():
                    try:
                        child.rmdir()
                    except Exception:
                        pass
            path.rmdir()
        except Exception:
            pass

    def _resolve_install_target_marker_path(self) -> Path:
        try:
            from path_utils import get_app_data_dir

            config_dir = Path(get_app_data_dir()) / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            return config_dir / "auto_update_target.json"
        except Exception:
            return self.update_cache_dir / "auto_update_target.json"

    def _resolve_transaction_journal_path(self) -> Path:
        try:
            return self.install_target_marker_path.parent / "auto_update_transaction.json"
        except Exception:
            return self.update_cache_dir / "auto_update_transaction.json"

    def _read_transaction(self) -> Dict[str, Any]:
        try:
            data = json.loads(self.transaction_journal_path.read_text(encoding="utf-8-sig"))
            return dict(data) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_transaction(self, phase: str, **updates: Any) -> Dict[str, Any]:
        data = dict(getattr(self, "transaction", {}) or {})
        data.update(updates)
        data["phase"] = str(phase)
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self.transaction_journal_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.transaction_journal_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.transaction_journal_path)
        except Exception as exc:
            self._log_warning(f"failed to persist update transaction: {exc}")
        self.transaction = data
        return dict(data)

    def _restore_pending_update(self) -> None:
        transaction = dict(getattr(self, "transaction", {}) or {})
        if str(transaction.get("phase") or "") not in {
            "downloaded",
            "preflight_approved",
            "preflight_blocked",
            "shutdown_failed",
            "shutdown_not_confirmed",
            "target_not_writable",
            "apply_scheduled",
            "replacing",
            "failed",
            "verification_failed",
            "apply_spawn_failed",
        }:
            return
        asset_path = Path(str(transaction.get("asset_path") or ""))
        if not asset_path.exists():
            return
        expected_sha = str(transaction.get("sha256") or "").lower()
        try:
            if not expected_sha or self._sha256_file(asset_path) != expected_sha:
                return
        except Exception:
            return
        self.pending_update = {
            "latest_version": str(transaction.get("new_version") or ""),
            "release_url": str(transaction.get("release_url") or ""),
            "asset_path": str(asset_path),
            "downloaded": True,
            "sha256": str(transaction.get("sha256") or ""),
            "verification": dict(transaction.get("verification") or {}),
        }
        self._apply_started = False

    def _check_install_target_replaceable(self, target_path: Path) -> Dict[str, Any]:
        """Fail early when the stable EXE target cannot be replaced safely."""
        if self._looks_like_update_cache_path(target_path):
            return {"ok": False, "reason": "install_target_is_update_cache"}
        if not target_path.is_file() or target_path.suffix.lower() != ".exe":
            return {"ok": False, "reason": "install_target_missing"}
        probe = target_path.parent / f".noah_update_write_probe_{os.getpid()}.tmp"
        try:
            probe.write_bytes(b"ok")
            probe.unlink()
        except Exception as exc:
            try:
                probe.unlink(missing_ok=True)
            except Exception:
                pass
            return {"ok": False, "reason": "install_target_directory_not_writable", "error": str(exc)}
        return {"ok": True, "reason": ""}

    @staticmethod
    def _is_path_under(path: Path, parent: Path) -> bool:
        try:
            path.resolve().relative_to(parent.resolve())
            return True
        except Exception:
            return False

    @staticmethod
    def _looks_like_update_cache_path(path: Path) -> bool:
        """Recognize staged executables even when a different cache root is active."""
        normalized = str(path or "").replace("\\", "/").lower()
        name = Path(normalized).name.lower()
        return (
            "/auto_updater/" in normalized
            or "/.auto_updater/" in normalized
            or name == "aitrading.new.exe"
        )

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
        if self._looks_like_update_cache_path(target_path):
            self._log_warning(f"refused to persist staged update target: {target_path}")
            return False
        try:
            self.install_target_marker_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "install_target_exe": str(target_path),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            self.install_target_marker_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def _recover_install_target_from_apply_scripts(self) -> Optional[Path]:
        """Recover the last stable EXE target from previously generated scripts."""
        search_roots = [self.update_cache_dir]
        try:
            sibling_cache = self.install_target_marker_path.parent.parent / "cache" / "auto_updater"
            if sibling_cache not in search_roots:
                search_roots.append(sibling_cache)
        except Exception:
            pass

        scripts = []
        for root in search_roots:
            try:
                scripts.extend(root.rglob("apply_update_*.ps1"))
            except Exception:
                continue
        try:
            scripts.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        except Exception:
            pass

        target_pattern = re.compile(r"(?im)^\s*\$target\s*=\s*'((?:[^']|'')+)'")
        for script_path in scripts:
            try:
                match = target_pattern.search(script_path.read_text(encoding="utf-8", errors="ignore"))
                if not match:
                    continue
                recovered = Path(match.group(1).replace("''", "'"))
                if (
                    recovered.suffix.lower() == ".exe"
                    and recovered.exists()
                    and not self._looks_like_update_cache_path(recovered)
                ):
                    self._persist_install_target(recovered)
                    self._log_info(f"recovered stable install target from apply script: {recovered}")
                    return recovered
            except Exception:
                continue
        return None

    def _resolve_install_target_executable(self) -> Path:
        current_exe = Path(sys.executable)
        if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
            return current_exe

        persisted = self._read_persisted_install_target()

        # 정상 경로에서 실행 중이면 그 경로를 설치 타겟으로 고정한다.
        if not self._looks_like_update_cache_path(current_exe):
            self._persist_install_target(current_exe)
            return current_exe

        # 캐시에서 실행된 경우에는 이전에 저장한 정상 타겟이 있으면 우선한다.
        if persisted and persisted.exists() and not self._looks_like_update_cache_path(persisted):
            self._log_info(
                f"current executable is in update cache; using persisted install target: {persisted}"
            )
            return persisted

        recovered = self._recover_install_target_from_apply_scripts()
        if recovered is not None:
            return recovered

        self._log_warning(
            "current executable is staged and no stable install target could be recovered; "
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
    def _build_apply_script(
        target_exe: str,
        new_exe: str,
        backup_exe: str,
        journal_path: str = "",
        expected_sha: str = "",
        old_version: str = "",
        new_version: str = "",
    ) -> str:
        target = target_exe.replace("'", "''")
        new = new_exe.replace("'", "''")
        backup = backup_exe.replace("'", "''")
        journal = journal_path.replace("'", "''")
        sha = expected_sha.replace("'", "''")
        old_v = old_version.replace("'", "''")
        new_v = new_version.replace("'", "''")
        return f"""
$ErrorActionPreference = 'Stop'
$target = '{target}'
$newExe = '{new}'
$backup = '{backup}'
$journal = '{journal}'
$expectedSha = '{sha}'
$oldVersion = '{old_v}'
$newVersion = '{new_v}'

function Set-Phase([string]$phase, [string]$detail = '') {{
    try {{
        if (Test-Path $journal) {{
            $state = Get-Content -Raw -Path $journal | ConvertFrom-Json
        }} else {{
            $state = [pscustomobject]@{{}}
        }}
        $state | Add-Member -NotePropertyName phase -NotePropertyValue $phase -Force
        $state | Add-Member -NotePropertyName detail -NotePropertyValue $detail -Force
        $state | Add-Member -NotePropertyName old_version -NotePropertyValue $oldVersion -Force
        $state | Add-Member -NotePropertyName new_version -NotePropertyValue $newVersion -Force
        $state | Add-Member -NotePropertyName target_path -NotePropertyValue $target -Force
        $state | Add-Member -NotePropertyName backup_path -NotePropertyValue $backup -Force
        $state | Add-Member -NotePropertyName sha256 -NotePropertyValue $expectedSha -Force
        $state | Add-Member -NotePropertyName updated_at -NotePropertyValue ((Get-Date).ToUniversalTime().ToString('o')) -Force
        $state | ConvertTo-Json -Depth 12 | Set-Content -Path $journal -Encoding UTF8
    }} catch {{
        # 저널 기록 실패 시에도 아래 안전 검증은 계속하며, 교체 전 단계에서는 실패 처리한다.
    }}
}}

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
    Set-Phase 'failed' 'staged executable missing'
    Restore-And-Start
    exit 1
}}

if ([string]::IsNullOrWhiteSpace($expectedSha)) {{
    Set-Phase 'failed' 'expected SHA256 missing'
    exit 1
}}

$actualSha = (Get-FileHash -Algorithm SHA256 -Path $newExe).Hash.ToLowerInvariant()
if ($actualSha -ne $expectedSha.ToLowerInvariant()) {{
    Set-Phase 'failed' 'staged SHA256 mismatch'
    exit 1
}}

if (-not (Test-Path $target)) {{
    Set-Phase 'failed' 'installed executable missing'
    exit 1
}}

try {{
    Copy-Item -Path $target -Destination $backup -Force
}} catch {{
    Set-Phase 'failed' ('backup failed: ' + $_.Exception.Message)
    exit 1
}}

Set-Phase 'replacing'
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
    Set-Phase 'failed' 'replacement failed'
    Restore-And-Start
    exit 1
}}

try {{
    $targetSha = (Get-FileHash -Algorithm SHA256 -Path $target).Hash.ToLowerInvariant()
    if ($targetSha -ne $expectedSha.ToLowerInvariant()) {{
        Set-Phase 'failed' 'installed SHA256 mismatch after replacement'
        Restore-And-Start
        exit 1
    }}
    # 새 프로세스가 health check를 시작하기 전에 상태를 기록한다. 부모
    # 스크립트가 이후 healthy 상태를 postcheck_pending으로 되돌리지 않는다.
    Set-Phase 'postcheck_pending'
    $proc = Start-Process -FilePath $target -PassThru
    Start-Sleep -Seconds 8
    Get-Process -Id $proc.Id -ErrorAction Stop | Out-Null
    exit 0
}} catch {{
    Set-Phase 'failed' ('launch failed: ' + $_.Exception.Message)
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

    def _emit_progress(self, **payload: Any):
        callback = self._progress_callback
        if not callable(callback):
            return
        try:
            callback(dict(payload))
        except Exception:
            pass

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
