from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyinstaller_tkinter_warnings_are_blocking():
    import build_safe

    messages = build_safe.find_blocking_pyinstaller_messages(
        "WARNING: tkinter installation is broken. It will be excluded from the application",
        "missing module named tkinter - imported by customtkinter",
    )

    assert len(messages) == 2
    assert build_safe.find_blocking_pyinstaller_messages("optional module named java") == []


def test_one_command_windows_release_contract():
    script = (ROOT / "scripts" / "build_release_windows.ps1").read_text(encoding="utf-8")

    assert "validate_windows_tkinter_build_runtime" in script
    assert "resolve_windows_vc_runtime_binaries" in script
    assert "build_windows_safe.ps1" in script
    assert "release_tag_push.ps1" in script
    assert "-SkipCommit" in script
    assert "AllowDirtyWorkingTree" in script
    assert "Get-FileHash" in script


def test_release_upload_requires_remote_digest_match():
    script = (ROOT / "scripts" / "release_tag_push.ps1").read_text(encoding="utf-8")

    assert "Assert-GhAuthenticated" in script
    assert "Assert-RemoteAssetMatches" in script
    assert 'AssetName "AITrading.exe"' in script
    assert 'AssetName "release-manifest.json"' in script
    assert "remote asset SHA-256 mismatch" in script


def test_builder_uses_atomic_deploy_replacement():
    source = (ROOT / "build_safe.py").read_text(encoding="utf-8")

    assert 'dest.with_suffix(dest.suffix + ".tmp")' in source
    assert "os.replace(temp_dest, dest)" in source
    assert "verify_windows_executable_version" in source
