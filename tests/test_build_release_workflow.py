from pathlib import Path

from config.app_version import RELEASE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_tkinter_warnings_are_blocking():
    import build_safe

    messages = build_safe.find_blocking_pyinstaller_messages(
        "WARNING: tkinter installation is broken. It will be excluded from the application",
        "missing module named tkinter - imported by customtkinter",
    )

    assert len(messages) == 2
    assert build_safe.find_blocking_pyinstaller_messages("optional module named java") == []


def test_web_engine_bundle_audit_requires_notification_runtime_module(tmp_path):
    from scripts.verify_web_engine_bundle import missing_required_runtime_modules

    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(repr([
        ("openai", "openai.pyc", "PYMODULE"),
        ("httpx", "httpx.pyc", "PYMODULE"),
        ("jiter", "jiter.pyd", "EXTENSION"),
    ]), encoding="utf-8")
    assert missing_required_runtime_modules(toc) == ["trading.notifications"]

    toc.write_text(repr([
        ("openai", "openai.pyc", "PYMODULE"),
        ("httpx", "httpx.pyc", "PYMODULE"),
        ("jiter", "jiter.pyd", "EXTENSION"),
        ("trading.notifications", "trading/notifications.pyc", "PYMODULE"),
    ]), encoding="utf-8")
    assert missing_required_runtime_modules(toc) == []


def test_one_command_windows_release_contract():
    script = (ROOT / "scripts" / "build_release_windows.ps1").read_text(encoding="utf-8")

    assert "validate_windows_tkinter_build_runtime" in script
    assert "resolve_windows_vc_runtime_binaries" in script
    assert "RELEASE_BUILD_LABEL" in script
    assert "(?i)\\b(fix|patch|hotfix)\\b" in script
    assert "same-version patch label detected" in script
    assert "build_windows_safe.ps1" in script
    assert "release_tag_push.ps1" in script
    assert "-SkipCommit" in script
    assert "AllowDirtyWorkingTree" in script
    assert "Get-FileHash" in script


def test_release_upload_requires_remote_digest_match():
    legacy_script = (ROOT / "scripts" / "release_tag_push.ps1").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")

    assert "v3.9.1.0+ uses the Electron bundle release contract" in legacy_script
    assert "Assert-RemoteDigest" in script
    assert "Assert-ParityLedgerComplete" in script
    assert "Get-PatchPlanPath" in script
    assert "Get-PatchPlanStatus" in script
    assert "V*_TEST_PLAN.md" in script
    assert "Multiple patch test plans found" in script
    assert "external_validation_pending_count" in script
    assert "Every required row must be [x] VERIFIED" in script
    for required_row in ("LOGIN-01", "BC-01", "STOCK-01", "PORT-01", "LIFE-01", "ANALYST-01", "SET-01", "MAN-01"):
        assert f'"{required_row}"' in script
    assert "windows_verified_release_candidate" in script
    assert "windows_automated_checks_passed" in script
    assert "latest.yml does not reference the built installer" in script
    assert "Manifest updater_semver is missing" in script
    assert "latest.yml updater version mismatch" in script
    assert "Remote digest mismatch" in script


def test_release_fingerprint_covers_engine_web_and_packaged_inputs(tmp_path):
    from scripts.release_source_fingerprint import (
        compute_release_source_fingerprint,
        release_source_files,
    )

    files = {
        path.relative_to(ROOT).as_posix() for path in release_source_files(ROOT)
    }
    for required in (
        "trading/trader.py",
        "trading/unified_trader.py",
        "trading/notifications.py",
        "trading/position_limit_policy.py",
        "strategy_customizer.py",
        "web_platform/runtime_bridge.py",
        "webui/src/components/LegacyFeatureWorkspaces.tsx",
        "docs/USER_MANUAL_SECTIONS.json",
        "docs/NOTIFICATION_INTEGRATIONS_GUIDE.md",
        "data/finance_products/loans.json",
        "noahai_web_engine.spec",
        "noahai_kiwoom_host.spec",
        "requirements_windows.txt",
        "requirements_kiwoom_x86.txt",
        "scripts/kiwoom_host.py",
        "scripts/runtime_soak_monitor.py",
    ):
        assert required in files

    (tmp_path / "trading").mkdir()
    engine = tmp_path / "trading" / "trader.py"
    engine.write_text("CAP = 1\n", encoding="utf-8")
    first = compute_release_source_fingerprint(tmp_path)
    engine.write_text("CAP = 3\n", encoding="utf-8")
    second = compute_release_source_fingerprint(tmp_path)
    assert first != second


def test_windows_build_and_publish_use_same_cross_platform_fingerprint():
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")
    publish_script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")

    for source in (build_script, publish_script):
        assert "Get-ReleaseSourceFingerprint" in source
        assert "scripts/release_source_fingerprint.py --root $Root" in source
        assert "^[0-9a-f]{64}$" in source


def test_windows_operator_override_does_not_hide_missing_kiwoom_host_gate():
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")
    build_wrapper = (ROOT / "scripts" / "build_windows.ps1").read_text(encoding="utf-8")
    one_shot = (ROOT / "scripts" / "build_and_release_windows.ps1").read_text(encoding="utf-8")

    assert "AllowMissingKiwoomHost" in build_script
    assert "Kiwoom remains an external gate" in build_script
    assert "AllowMissingKiwoomHost" in build_wrapper
    assert "AllowMissingKiwoomHost) { $buildArgs += \"-AllowMissingKiwoomHost\" }" in one_shot
    assert "AllowMissingKiwoomHost -or $AllowPendingExternalGates" not in one_shot


def test_release_manifest_and_publisher_verify_packaged_kiwoom_host():
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")
    publish_script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")
    host_spec = (ROOT / "noahai_kiwoom_host.spec").read_text(encoding="utf-8")
    host_version = (ROOT / "config" / "windows_kiwoom_host_version_info.txt").read_text(encoding="utf-8")

    assert "Verify packaged Kiwoom host PE architecture" in build_script
    assert "Packaged Kiwoom host SHA-256 mismatch" in build_script
    assert "kiwoom_host = [ordered]@{" in build_script
    assert "assets.kiwoom_host.supported -ne $true" in publish_script
    assert "Kiwoom host PE architecture verification failed" in publish_script
    assert 'version="config/windows_kiwoom_host_version_info.txt"' in host_spec
    assert '"log_system.log_stream"' in host_spec
    assert f"FileVersion', u'{RELEASE_VERSION}'" in host_version
    assert "OriginalFilename', u'NoahAIKiwoomHost.exe'" in host_version


def test_external_validation_is_reported_without_blocking_stable_release():
    script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")

    assert 'build_status = "windows_verified_release_candidate"' in script
    assert 'channel = "stable"' in script
    assert '$manifest.publish_ready = $true' in script
    assert 'gh release create $tag --repo $Repo --target $releaseTarget --draft' in script
    assert '--draft=false --prerelease=false --latest' in script
    assert 'automated_checks_passed -ne $true' in script
    assert 'Assert-RemoteDigest $tag $asset' in script
    assert "Release notes do not describe v$version" in script


def test_default_wrappers_publish_after_automated_checks_without_gate_override():
    script = (ROOT / "scripts" / "publish_web_ui_windows_release.ps1").read_text(encoding="utf-8")
    release_wrapper = (ROOT / "scripts" / "release_windows.ps1").read_text(encoding="utf-8")
    one_shot = (ROOT / "scripts" / "build_and_release_windows.ps1").read_text(encoding="utf-8")

    for source in (script, release_wrapper, one_shot):
        assert "PublishStableWithPendingExternalGates" not in source
        assert "AllowPendingExternalGates" not in source
    assert "Get-PatchPlanStatus" in script
    assert "external_validation_status" in script


def test_windows_rebuild_resets_same_version_published_manifest_to_pending():
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")

    assert '$ExistingManifest.build_status -eq "pending_windows_rebuild"' in build_script
    assert "pending_windows_rebuild" in build_script


def test_electron_product_version_has_monotonic_updater_semver_guard():
    package = (ROOT / "webui" / "package.json").read_text(encoding="utf-8")
    build_script = (ROOT / "scripts" / "build_web_ui_windows.ps1").read_text(encoding="utf-8")
    electron = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    major, minor, patch, revision = (int(part) for part in RELEASE_VERSION.split("."))
    updater_version = f"{major}.{minor}.{patch * 100 + revision}"

    assert f'"version": "{updater_version}"' in package
    assert f'"buildVersion": "{RELEASE_VERSION}"' in package
    assert "C*100+D" in build_script
    assert 'RELEASE_VERSION >= 3.9.1.0' in build_script
    assert "Electron updater version mismatch" in build_script
    assert "Electron package-lock updater version mismatch" in build_script
    assert "latest.yml updater version mismatch" in build_script
    assert "currentProductVersion" in electron


def test_github_workflow_builds_candidate_before_explicit_release():
    workflow = (ROOT / ".github" / "workflows" / "windows-release.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "build_web_ui_windows.ps1" in workflow
    assert "upload-artifact@v4" in workflow
    assert "NOAHAI_PYTHON_X86" in workflow
    assert "requirements_kiwoom_x86.txt" in workflow
    assert "confirm_external_gates" not in workflow
    assert "publish_web_ui_windows_release.ps1" in workflow
    assert "ConfirmExternalGates" not in workflow
    assert "softprops/action-gh-release" not in workflow  # no second publisher bypassing guards
    assert "deploy/web-release/NoahAI-${{ steps.app_version.outputs.version }}-Setup.exe" in workflow
    assert "latest.yml" in workflow
    assert ".blockmap" in workflow


def test_macos_publisher_uses_shared_product_release_tag():
    build_script = (ROOT / "scripts" / "build_macos.py").read_text(encoding="utf-8")
    publish_script = (ROOT / "scripts" / "publish_macos.py").read_text(encoding="utf-8")

    assert 'tag = f"v{RELEASE_VERSION}"' in publish_script
    assert "macos-candidate" not in publish_script
    assert "Published asset differs; bump the product version" in publish_script
    assert 'f"NoahAI-{RELEASE_VERSION}-arm64.zip.blockmap"' in build_script
    assert 'f"NoahAI-{RELEASE_VERSION}-arm64.dmg.blockmap"' in build_script


def test_release_manifest_records_source_revision():
    source = (ROOT / "scripts" / "generate_release_assets.py").read_text(encoding="utf-8")

    assert "def _source_revision()" in source
    assert '"source_revision": _source_revision()' in source
    assert '"dirty": bool(status)' in source


def test_builder_uses_atomic_deploy_replacement():
    source = (ROOT / "build_safe.py").read_text(encoding="utf-8")

    assert 'dest.with_suffix(dest.suffix + ".tmp")' in source
    assert "os.replace(temp_dest, dest)" in source
    assert "verify_windows_executable_version" in source
