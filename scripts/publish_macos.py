#!/usr/bin/env python3
"""Upload immutable macOS assets to the shared product-version release."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from config.app_version import RELEASE_VERSION
from scripts.release_source_fingerprint import compute_release_source_fingerprint
from scripts.verify_release_provenance import verify_source, verify_remote


def main():
    folder = ROOT / "deploy/mac-release"
    manifest_path = folder / "release-manifest-mac.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["version"] != RELEASE_VERSION or manifest["source_fingerprint"] != compute_release_source_fingerprint(ROOT):
        raise RuntimeError("Stale macOS candidate; rebuild before upload")
    files = [manifest_path]
    for asset in manifest["assets"]:
        path = folder / asset["name"]
        if path.parent != folder or path.stat().st_size != asset["size"] or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise RuntimeError("Candidate file/hash mismatch")
        files.append(path)
    repo = "nwsoft/ai-trading-client"
    tag = f"v{RELEASE_VERSION}"
    release_target = verify_source(ROOT, manifest)
    verify_remote(repo, tag, release_target)
    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo,
         "--json", "isDraft,isPrerelease,assets"],
        capture_output=True, text=True,
    )
    if existing.returncode == 0:
        release = json.loads(existing.stdout)
        if not release["isDraft"] and not release["isPrerelease"] and not manifest["signed_notarized"]:
            raise RuntimeError("Unsigned macOS assets cannot be added to a stable release")
    else:
        subprocess.run(["gh", "release", "create", tag, "--repo", repo, "--draft", "--prerelease",
                        "--target", release_target,
                        "--title", tag,
                        "--notes", "Shared Windows/macOS release draft. Platform assets and external gates are incomplete."], check=True)
        release = {"isDraft": True, "isPrerelease": True, "assets": []}

    verify_remote(repo, tag, release_target, require_tag=True)

    remote_by_name = {item["name"]: item for item in release["assets"]}
    for path in files:
        expected_digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        existing_asset = remote_by_name.get(path.name)
        if existing_asset:
            if existing_asset["size"] != path.stat().st_size or existing_asset.get("digest") != expected_digest:
                raise RuntimeError(f"Published asset differs; bump the product version: {path.name}")
            continue
        subprocess.run(["gh", "release", "upload", tag, "--repo", repo, str(path)], check=True)

    remote = json.loads(subprocess.check_output(
        ["gh", "release", "view", tag, "--repo", repo,
         "--json", "isDraft,isPrerelease,assets"], text=True,
    ))
    for path in files:
        row = next(item for item in remote["assets"] if item["name"] == path.name)
        if row["size"] != path.stat().st_size or row.get("digest") != "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest():
            raise RuntimeError("Remote asset verification failed")
    state = "draft" if remote["isDraft"] else "prerelease" if remote["isPrerelease"] else "stable"
    print(f"Shared release upload and remote SHA-256 verified: {tag} ({state})")


if __name__ == "__main__":
    main()
