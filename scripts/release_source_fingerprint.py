#!/usr/bin/env python3
"""Compute one cross-platform fingerprint for every Windows release input.

The previous PowerShell-only implementation covered the Web gateway and React
shell but omitted the trading engine itself.  A candidate could therefore look
current after ``trading/trader.py`` or an exchange adapter changed.  Build and
publish now call this single implementation so their file set cannot drift.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path(__file__).resolve().parents[1]

DIRECTORY_RULES: tuple[tuple[str, frozenset[str] | None], ...] = (
    ("analytics", frozenset({".py"})),
    ("api", frozenset({".py"})),
    ("config", frozenset({".py", ".json", ".yaml", ".yml"})),
    ("hooks", frozenset({".py"})),
    ("log_system", frozenset({".py"})),
    ("trading", frozenset({".py"})),
    ("utils", frozenset({".py"})),
    ("web_platform", frozenset({".py"})),
    ("webui/src", frozenset({".ts", ".tsx", ".css", ".json"})),
    ("webui/electron", frozenset({".js", ".cjs", ".json"})),
    ("webui/public", None),
    ("data/finance_products", frozenset({".json"})),
)

EXPLICIT_FILES = (
    ".gitattributes",
    ".github/workflows/windows-release.yml",
    "deploy/release_notes.md",
    "docs/USER_GUIDE.md",
    "docs/USER_MANUAL_SECTIONS.json",
    "docs/NOTIFICATION_INTEGRATIONS_GUIDE.md",
    "docs/REMOTE_MANAGEMENT_GUIDE_V39141.md",
    "docs/REMOTE_MANAGEMENT_GUIDE_V39142.md",
    "config/windows_version_info.txt",
    "config/windows_kiwoom_host_version_info.txt",
    "icon.ico",
    "icon.png",
    "noahai_web_engine.spec",
    "scripts/build_macos.py",
    "scripts/publish_macos.py",
    "scripts/smoke_kiwoom_host.py",
    "webui/electron-builder.mac.cjs",
    "noahai_kiwoom_host.spec",
    "requirements.txt",
    "requirements_kiwoom_x86.txt",
    "requirements_windows.txt",
    "requirements_macos.txt",
    "scripts/build_and_release_windows.ps1",
    "scripts/build_web_ui_windows.ps1",
    "scripts/build_windows.ps1",
    "scripts/export_legacy_manual_sections.py",
    "scripts/export_strategy_venue_registry.py",
    "scripts/kiwoom_host.py",
    "scripts/publish_web_ui_windows_release.ps1",
    "scripts/release_windows.ps1",
    "scripts/release_source_fingerprint.py",
    "scripts/verify_release_provenance.py",
    "scripts/runtime_soak_monitor.py",
    "ui/ai_custom_guidance.py",
    "ui/live_trading_guidance.py",
    "ui/widgets/user_manual_widget.py",
    "webui/index.html",
    "webui/package.json",
    "webui/package-lock.json",
    "webui/tsconfig.app.json",
    "webui/tsconfig.json",
    "webui/tsconfig.node.json",
    "webui/vite.config.ts",
)


def _eligible(path: Path, extensions: frozenset[str] | None) -> bool:
    return path.is_file() and (extensions is None or path.suffix.lower() in extensions)


def release_source_files(root: Path = DEFAULT_ROOT) -> list[Path]:
    """Return the normalized, unique release input set below ``root``."""
    root = root.resolve()
    files: set[Path] = set()
    for path in root.glob("*.py"):
        if path.is_file():
            files.add(path.resolve())
    for relative_dir, extensions in DIRECTORY_RULES:
        directory = root / relative_dir
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if _eligible(path, extensions):
                files.add(path.resolve())
    for relative in EXPLICIT_FILES:
        path = root / relative
        if path.is_file():
            files.add(path.resolve())
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def fingerprint_rows(root: Path = DEFAULT_ROOT) -> Iterable[str]:
    root = root.resolve()
    for path in release_source_files(root):
        relative = path.relative_to(root).as_posix()
        yield f"{relative}={hashlib.sha256(path.read_bytes()).hexdigest()}"


def compute_release_source_fingerprint(root: Path = DEFAULT_ROOT) -> str:
    rows = "\n".join(fingerprint_rows(root)).encode("utf-8")
    return hashlib.sha256(rows).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="NoahAI Windows release source fingerprint")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--list", action="store_true", help="Print normalized input paths before the digest")
    args = parser.parse_args()
    root = args.root.resolve()
    files = release_source_files(root)
    if not files:
        raise SystemExit("release fingerprint input set is empty")
    if args.list:
        for path in files:
            print(path.relative_to(root).as_posix())
    print(compute_release_source_fingerprint(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
