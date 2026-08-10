import builtins
import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_chart_analyzer_import_does_not_load_native_ocr_engines(monkeypatch):
    module_name = "trading.ai.chart_screenshot_analyzer"
    sys.modules.pop(module_name, None)
    attempted = []
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith(("rapidocr_onnxruntime", "onnxruntime", "paddleocr", "paddle", "cv2")):
            attempted.append(name)
            raise AssertionError(f"dashboard import 중 네이티브 OCR 로드: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    imported = importlib.import_module(module_name)

    assert imported._RAPID_OCR_IMPORT_ATTEMPTED is False
    assert imported._PADDLE_OCR_IMPORT_ATTEMPTED is False
    assert attempted == []


def test_rapidocr_is_created_only_when_ocr_is_requested(monkeypatch):
    from trading.ai import chart_screenshot_analyzer as analyzer_module

    created = []

    class FakeRapidOCR:
        def __init__(self):
            created.append(True)

    monkeypatch.setattr(analyzer_module, "_load_rapid_ocr_class", lambda: FakeRapidOCR)
    analyzer = analyzer_module.ChartScreenshotAnalyzer(disable_ocr=False)

    assert created == []
    assert isinstance(analyzer._get_rapid_ocr(), FakeRapidOCR)
    assert created == [True]


def test_vc_runtime_directory_rejects_mixed_or_old_sets(tmp_path, monkeypatch):
    import build_safe

    for name in build_safe.WINDOWS_VC_RUNTIME_REQUIRED:
        (tmp_path / name).write_bytes(name.encode("ascii"))

    versions = {
        name: (14, 51, 12345, 0)
        for name in build_safe.WINDOWS_VC_RUNTIME_REQUIRED
    }
    monkeypatch.setattr(
        build_safe,
        "_windows_file_version",
        lambda path: versions[path.name],
    )
    selected = build_safe.validate_vc_runtime_dir(tmp_path, (14, 40, 0, 0))
    assert {name for name, _ in selected} == set(build_safe.WINDOWS_VC_RUNTIME_REQUIRED)

    versions["msvcp140.dll"] = (14, 26, 28720, 3)
    with pytest.raises(RuntimeError, match="오래된 VC 런타임"):
        build_safe.validate_vc_runtime_dir(tmp_path, (14, 40, 0, 0))

    versions["msvcp140.dll"] = (14, 50, 10000, 0)
    with pytest.raises(RuntimeError, match="서로 다른 VC 런타임 세트"):
        build_safe.validate_vc_runtime_dir(tmp_path, (14, 40, 0, 0))

    assert build_safe.is_windows_vc_runtime_name("PyQt5/Qt5/bin/MSVCP140_future.dll")
    assert build_safe.is_windows_vc_runtime_name("pandas/VCRUNTIME140_1.dll")
    assert not build_safe.is_windows_vc_runtime_name("Qt5Core.dll")


def test_automatic_vc_runtime_selection_uses_highest_official_version(tmp_path, monkeypatch):
    import build_safe

    old_dir = tmp_path / "14.40" / "Microsoft.VC143.CRT"
    new_dir = tmp_path / "14.51" / "Microsoft.VC143.CRT"
    old_dir.mkdir(parents=True)
    new_dir.mkdir(parents=True)
    monkeypatch.setattr(build_safe.sys, "platform", "win32")
    monkeypatch.delenv(build_safe.WINDOWS_VC_RUNTIME_ENV, raising=False)
    monkeypatch.setattr(build_safe, "required_vc_runtime_version", lambda: (14, 40, 0, 0))
    monkeypatch.setattr(build_safe, "_vc_runtime_candidate_dirs", lambda: [old_dir, new_dir])
    monkeypatch.setattr(
        build_safe,
        "validate_vc_runtime_dir",
        lambda runtime_dir, minimum: [("msvcp140.dll", str(runtime_dir / "msvcp140.dll"))],
    )
    monkeypatch.setattr(
        build_safe,
        "_windows_file_version",
        lambda path: (14, 51, 1, 0) if "14.51" in str(path) else (14, 40, 1, 0),
    )

    selected = build_safe.resolve_windows_vc_runtime_binaries()

    assert "14.51" in selected[0][1]


def test_generated_windows_spec_removes_nested_vc_dlls_and_keeps_pyqt(tmp_path, monkeypatch):
    import build_safe

    fake_runtime = [
        (name, str(tmp_path / name))
        for name in build_safe.WINDOWS_VC_RUNTIME_REQUIRED
    ]
    monkeypatch.setattr(
        build_safe,
        "resolve_windows_vc_runtime_binaries",
        lambda: fake_runtime,
    )
    monkeypatch.setattr(
        build_safe,
        "validate_windows_tkinter_build_runtime",
        lambda: True,
    )
    spec_path = tmp_path / "aiautotrade_safe.spec"
    build_safe.create_safe_spec_file("windows", str(spec_path))
    source = spec_path.read_text(encoding="utf-8")

    assert "PyQt5.QAxContainer" in source
    assert "_NOAHAI_VC_RUNTIME_NAMES" in source
    assert "_noahai_bundle_basename" in source
    assert "_noahai_is_vc_runtime" in source
    assert "a.binaries = [" in source
    assert "msvcp140.dll" in source
    assert "vcruntime140_1.dll" in source


def test_windows_dependencies_are_pinned_for_reproducible_native_build():
    requirements = (ROOT / "requirements_windows.txt").read_text(encoding="utf-8")
    for marker in (
        "PyInstaller==6.21.0",
        "PyQt5==5.15.11",
        "PyQt5-Qt5==5.15.2",
        "rapidocr-onnxruntime==1.2.3",
        "onnxruntime==1.23.1",
    ):
        assert marker in requirements


def test_builder_returns_failure_when_native_archive_verification_fails(monkeypatch):
    import build_safe

    monkeypatch.setattr(build_safe.sys, "argv", ["build_safe.py", "--platform", "windows", "--skip-gate"])
    monkeypatch.setattr(build_safe, "ensure_build_dependencies", lambda platform: True)
    monkeypatch.setattr(build_safe, "create_safe_build_environment", lambda: [])
    monkeypatch.setattr(build_safe, "create_safe_spec_file", lambda platform: "aiautotrade_safe.spec")
    monkeypatch.setattr(build_safe, "build_exe", lambda: True)
    monkeypatch.setattr(build_safe, "verify_safe_build", lambda platform: False)
    monkeypatch.setattr(build_safe, "restore_files_after_build", lambda files: None)

    assert build_safe.main() == 1
