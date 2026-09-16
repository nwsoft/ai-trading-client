#!/usr/bin/env python3
"""Build native arm64 assets for the shared cross-platform release."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.app_version import RELEASE_VERSION
from scripts.release_source_fingerprint import compute_release_source_fingerprint


def run(command, *, env=None):
    print("BUILD:", " ".join(map(str, command)), flush=True)
    subprocess.run(list(map(str, command)), cwd=ROOT, env=env, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--signed", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin" or platform.machine() != "arm64":
        parser.error("Build on native macOS arm64; Intel/universal is not verified")
    if args.signed and not os.environ.get("CSC_NAME"):
        parser.error("Signed build requires Developer ID CSC_NAME and Apple notarization environment")
    env = {**os.environ, "NOAHAI_MAC_SIGNED": "1" if args.signed else "0"}
    if not args.signed:
        env["CSC_IDENTITY_AUTO_DISCOVERY"] = "false"
    py = sys.executable
    from importlib.metadata import version
    for line in (ROOT / "requirements_macos.txt").read_text().splitlines():
        if "==" in line and not line.startswith("#"):
            package, expected = line.split("==", 1)
            if version(package) != expected:
                raise RuntimeError(f"Install requirements_macos.txt first: {package} version mismatch")
    run([py, "-c", "from rapidocr_onnxruntime import RapidOCR; RapidOCR(); from pypdf import PdfReader; import youtube_transcript_api, yt_dlp; print('MAC OCR/PDF/source dependency preflight PASS')"])
    run([py, "scripts/export_legacy_manual_sections.py"])
    run([py, "scripts/doc_consistency_check.py"])
    run(["npm", "--prefix", "webui", "ci", "--include=optional"])
    run([py, "-m", "pytest", "-q"])
    run(["npm", "--prefix", "webui", "run", "build"])
    fingerprint = compute_release_source_fingerprint(ROOT)
    revision_result = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    source_revision = revision_result.stdout.strip() if revision_result.returncode == 0 else None
    run([py, "-m", "PyInstaller", "--noconfirm", "--distpath", "deploy/mac-engine",
         "--workpath", "build/mac-engine", "noahai_web_engine.spec"])
    engine = ROOT / "deploy/mac-engine/noahai-engine"
    run([py, "scripts/smoke_web_engine.py", engine])
    run(["npm", "--prefix", "webui", "exec", "--", "electron-builder", "--projectDir", "webui",
         "--config", "electron-builder.mac.cjs", "--mac", "--arm64", "--publish", "never"], env=env)
    release = ROOT / "deploy/mac-release"
    app = release / "mac-arm64/NoahAI.app"
    run([py, "scripts/smoke_web_engine.py", app / "Contents/Resources/engine/noahai-engine"])
    if args.signed:
        run(["codesign", "--verify", "--deep", "--strict", app])
        run(["spctl", "--assess", "--type", "execute", app])
    if compute_release_source_fingerprint(ROOT) != fingerprint:
        raise RuntimeError("Source changed during build; candidate must be rebuilt")
    assets = []
    for name in (
        f"NoahAI-{RELEASE_VERSION}-arm64.dmg",
        f"NoahAI-{RELEASE_VERSION}-arm64.dmg.blockmap",
        f"NoahAI-{RELEASE_VERSION}-arm64.zip",
        f"NoahAI-{RELEASE_VERSION}-arm64.zip.blockmap",
        "latest-mac.yml",
    ):
        path = release / name
        assets.append({"name": name, "size": path.stat().st_size,
                       "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = {"version": RELEASE_VERSION, "platform": "darwin", "arch": "arm64",
                "source_fingerprint": fingerprint, "source_revision": source_revision,
                "channel": "shared_release_pending", "publish_ready": False,
                "signed_notarized": args.signed, "build_status": "mac_built_external_gates_pending",
                "generated_at": datetime.now(timezone.utc).isoformat(), "assets": assets,
                "external_gates": ["mac_install_upgrade", "mac_account_e2e", "paper_soak"] + ([] if args.signed else ["developer_id_notarization"])}
    (release / "release-manifest-mac.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("MAC CANDIDATE BUILT:", release, "(not a verified stable release)")


if __name__ == "__main__":
    main()
