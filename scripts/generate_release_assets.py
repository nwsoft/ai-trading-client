#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""릴리즈 배포 자산(version.txt/release_notes/manifest)을 생성한다."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _read_release_version() -> str:
    from config.app_version import RELEASE_VERSION

    return str(RELEASE_VERSION).strip()


def _read_release_label() -> str:
    from config.app_version import RELEASE_BUILD_LABEL

    return str(RELEASE_BUILD_LABEL).strip()


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


def _git_value(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return ""
    return result.stdout.strip()


def _source_revision() -> dict:
    commit = _git_value("rev-parse", "HEAD")
    short_commit = _git_value("rev-parse", "--short", "HEAD")
    status = _git_value("status", "--porcelain")
    return {
        "commit": commit,
        "short_commit": short_commit,
        "dirty": bool(status),
    }


def _latest_runtime_source() -> Path:
    """Windows 실행 파일에 포함되는 최신 런타임 소스를 반환한다."""
    source_files = [
        PROJECT_ROOT / "main.py",
        PROJECT_ROOT / "build_safe.py",
        PROJECT_ROOT / "aiautotrade.spec",
        PROJECT_ROOT / "config" / "app_version.py",
        PROJECT_ROOT / "config" / "windows_version_info.txt",
    ]
    for directory in ("api", "config", "trading", "ui", "utils"):
        source_files.extend(
            path
            for path in (PROJECT_ROOT / directory).rglob("*.py")
            if "__pycache__" not in path.parts
        )
    existing_sources = [path for path in source_files if path.exists()]
    if not existing_sources:
        return PROJECT_ROOT / "config" / "app_version.py"
    return max(existing_sources, key=lambda path: path.stat().st_mtime)


def _build_manifest(
    version: str,
    release_label: str,
    exe_path: Path,
    notes_path: Path,
    repo: str,
    previous_exe_path: Path | None = None,
    previous_version: str = "",
    previous_release_label: str = "",
) -> dict:
    has_exe = exe_path.exists()
    exe_name = exe_path.name

    manifest = {
        "version": version,
        "release_label": release_label,
        "channel": "stable",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "build_status": "built" if has_exe else "pending_windows_rebuild",
        "notes_file": notes_path.name,
        "verification": {
            "sha256_required": True,
            "authenticode_required": False,
            "source": "github_release_manifest",
        },
        "source_revision": _source_revision(),
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
    if previous_exe_path is not None and previous_exe_path.is_file():
        try:
            relative_path = previous_exe_path.resolve().relative_to(PROJECT_ROOT.resolve())
            stored_path = relative_path.as_posix()
        except ValueError:
            stored_path = str(previous_exe_path)
        manifest["previous_published_asset"] = {
            "version": previous_version or version,
            "release_label": previous_release_label,
            "purpose": "previous_published_windows_build",
            "path": stored_path,
            "size": previous_exe_path.stat().st_size,
            "sha256": _sha256_of(previous_exe_path),
        }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release assets for GitHub release")
    parser.add_argument("--out-dir", default="deploy", help="Output directory (default: deploy)")
    parser.add_argument("--exe", default="deploy/AITrading.exe", help="Path to AITrading.exe")
    parser.add_argument("--changelog", default="docs/CHANGELOG.md", help="Path to changelog")
    parser.add_argument("--repo", default="nwsoft/ai-trading-client", help="GitHub repository owner/name")
    parser.add_argument(
        "--previous-exe",
        default="deploy/previous/AITrading-v3.9.0.8-AI-Custom-Update.exe",
        help="직전 공개 Windows EXE 보존 경로",
    )
    parser.add_argument(
        "--previous-release-label",
        default="v3.9.0.8 AI Custom Update",
        help="직전 공개 Windows EXE 릴리스 표기",
    )
    parser.add_argument(
        "--previous-version",
        default="3.9.0.8",
        help="직전 공개 Windows EXE 버전",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    exe_path = Path(args.exe)
    changelog_path = Path(args.changelog)

    out_dir.mkdir(parents=True, exist_ok=True)

    version = _read_release_version()
    release_label = _read_release_label()
    latest_runtime_source = _latest_runtime_source()
    if exe_path.exists() and exe_path.stat().st_mtime < latest_runtime_source.stat().st_mtime:
        print(
            "error: AITrading.exe가 최신 런타임 소스보다 오래된 빌드입니다. "
            f"최신 파일: {latest_runtime_source.relative_to(PROJECT_ROOT)}. "
            "Windows에서 현재 소스를 다시 빌드한 뒤 릴리스 자산을 생성하세요."
        )
        return 2
    previous_exe_path = Path(args.previous_exe)
    if (
        exe_path.exists()
        and previous_exe_path.is_file()
        and _sha256_of(exe_path) == _sha256_of(previous_exe_path)
        and release_label.strip() != args.previous_release_label.strip()
    ):
        print(
            "error: AITrading.exe SHA-256이 previous_published_asset과 같습니다. "
            f"current={release_label}, previous={args.previous_release_label}. "
            "Fix Patch 릴리스에는 새 Windows 빌드 산출물이 필요합니다."
        )
        return 2
    notes_text = _extract_latest_changelog_section(changelog_path)

    version_path = out_dir / "version.txt"
    notes_path = out_dir / "release_notes.md"
    manifest_path = out_dir / "release-manifest.json"

    version_path.write_text(f"{version}\n", encoding="utf-8")
    notes_path.write_text(notes_text + "\n", encoding="utf-8")

    manifest = _build_manifest(
        version=version,
        release_label=release_label,
        exe_path=exe_path,
        notes_path=notes_path,
        repo=args.repo,
        previous_exe_path=previous_exe_path,
        previous_version=args.previous_version,
        previous_release_label=args.previous_release_label,
    )
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"version: {version}")
    print(f"release_label: {release_label}")
    print(f"written: {version_path}")
    print(f"written: {notes_path}")
    print(f"written: {manifest_path}")
    if not exe_path.exists():
        print(f"warning: exe not found at {exe_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
