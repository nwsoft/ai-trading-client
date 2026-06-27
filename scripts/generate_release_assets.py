#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""릴리즈 배포 자산(version.txt/release_notes/manifest)을 생성한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_release_version() -> str:
    from config.app_version import RELEASE_VERSION

    return str(RELEASE_VERSION).strip()


def _extract_latest_changelog_section(changelog_path: Path) -> str:
    if not changelog_path.exists():
        return "최신 변경 내역 문서를 찾을 수 없습니다."

    text = changelog_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    start = None
    for idx, line in enumerate(lines):
        if line.startswith("## "):
            start = idx
            break

    if start is None:
        return text.strip() or "변경 내역이 비어 있습니다."

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break

    section = "\n".join(lines[start:end]).strip()
    return section or "최신 변경 내역을 추출하지 못했습니다."


def _sha256_of(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_manifest(version: str, exe_path: Path, notes_path: Path, repo: str) -> dict:
    has_exe = exe_path.exists()
    exe_name = exe_path.name

    manifest = {
        "version": version,
        "channel": "stable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "notes_file": notes_path.name,
        "assets": {
            "exe": {
                "name": exe_name,
                "size": exe_path.stat().st_size if has_exe else 0,
                "sha256": _sha256_of(exe_path) if has_exe else "",
                "download_url": f"https://github.com/{repo}/releases/download/v{version}/{exe_name}",
            },
            "version_file": {
                "name": "version.txt",
                "download_url": f"https://github.com/{repo}/releases/download/v{version}/version.txt",
            },
        },
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release assets for GitHub release")
    parser.add_argument("--out-dir", default="deploy", help="Output directory (default: deploy)")
    parser.add_argument("--exe", default="deploy/AITrading.exe", help="Path to AITrading.exe")
    parser.add_argument("--changelog", default="docs/CHANGELOG.md", help="Path to changelog")
    parser.add_argument("--repo", default="nwsoft/ai-trading-client", help="GitHub repository owner/name")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    exe_path = Path(args.exe)
    changelog_path = Path(args.changelog)

    out_dir.mkdir(parents=True, exist_ok=True)

    version = _read_release_version()
    notes_text = _extract_latest_changelog_section(changelog_path)

    version_path = out_dir / "version.txt"
    notes_path = out_dir / "release_notes.md"
    manifest_path = out_dir / "release-manifest.json"

    version_path.write_text(f"{version}\n", encoding="utf-8")
    notes_path.write_text(notes_text + "\n", encoding="utf-8")

    manifest = _build_manifest(version=version, exe_path=exe_path, notes_path=notes_path, repo=args.repo)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"version: {version}")
    print(f"written: {version_path}")
    print(f"written: {notes_path}")
    print(f"written: {manifest_path}")
    if not exe_path.exists():
        print(f"warning: exe not found at {exe_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
