from pathlib import Path

from scripts.verify_web_engine_bundle import forbidden_modules, missing_required_ai_runtime_modules


def test_forbidden_modules_ignores_analysis_exclude_list(tmp_path: Path):
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(
        repr(([], [], [], [], {}, ["main", "ui", "tkinter"], [("gateway", "gateway.py", "PYMODULE")])),
        encoding="utf-8",
    )

    assert forbidden_modules(toc) == []


def test_forbidden_modules_detects_collected_python_entries(tmp_path: Path):
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(
        repr(([("ui.dashboard", "ui/dashboard.py", "PYMODULE")],)),
        encoding="utf-8",
    )

    assert forbidden_modules(toc) == ["ui.dashboard"]


def test_forbidden_modules_detects_x86_only_kiwoom_dependencies(tmp_path: Path):
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(
        repr(([
            ("PyQt5.QAxContainer", "PyQt5/QAxContainer.pyd", "EXTENSION"),
            ("pykiwoom.kiwoom", "pykiwoom/kiwoom.pyc", "PYMODULE"),
        ],)),
        encoding="utf-8",
    )

    assert forbidden_modules(toc) == ["PyQt5.QAxContainer", "pykiwoom.kiwoom"]


def test_ai_provider_runtime_modules_are_required_in_sidecar_toc(tmp_path: Path):
    toc = tmp_path / "Analysis-00.toc"
    toc.write_text(
        repr(([
            ("openai", "openai/__init__.py", "PYMODULE"),
            ("httpx", "httpx/__init__.py", "PYMODULE"),
            ("jiter\\jiter.cp311-win_amd64.pyd", "jiter.pyd", "EXTENSION"),
        ],)),
        encoding="utf-8",
    )
    assert missing_required_ai_runtime_modules(toc) == []
