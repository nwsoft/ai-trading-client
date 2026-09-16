#!/usr/bin/env python3
"""Read-only release provenance and public ordering gates. Never moves tags."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.release_source_fingerprint import (
    DIRECTORY_RULES, EXPLICIT_FILES, compute_release_source_fingerprint,
)


def git(root, *args, input=None):
    return subprocess.run(['git', '-C', str(root), *args], input=input,
                          capture_output=True, check=True).stdout


def is_input(name):
    path = Path(name)
    if name in EXPLICIT_FILES or ('/' not in name and path.suffix == '.py'):
        return True
    return any(name.startswith(folder + '/') and (extensions is None or path.suffix.lower() in extensions)
               for folder, extensions in DIRECTORY_RULES)


def committed_fingerprint(root, revision):
    entries = []
    for row in git(root, 'ls-tree', '-rz', '--full-tree', revision).split(b'\0'):
        if not row:
            continue
        meta, raw_name = row.split(b'\t', 1)
        name = raw_name.decode('utf-8')
        mode, kind, oid = meta.split()
        if is_input(name):
            if kind != b'blob' or mode == b'120000':
                raise RuntimeError('Release input must be a regular committed file: ' + name)
            entries.append((name, oid))
    if not entries:
        raise RuntimeError('No committed release inputs')
    entries.sort()
    response = io.BytesIO(git(root, 'cat-file', '--batch', input=b''.join(oid + b'\n' for _, oid in entries)))
    rows = []
    for name, oid in entries:
        object_id, kind, size = response.readline().split()
        if object_id != oid or kind != b'blob':
            raise RuntimeError('Invalid Git object response')
        content = response.read(int(size))
        if response.read(1) != b'\n':
            raise RuntimeError('Invalid Git object boundary')
        rows.append(name + '=' + hashlib.sha256(content).hexdigest())
    return hashlib.sha256('\n'.join(rows).encode()).hexdigest()


def verify_source(root, manifest):
    revision = str(manifest.get('source_revision') or '')
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('A committed build source_revision is required; no remote-main fallback')
    if git(root, 'rev-parse', 'HEAD').decode().strip() != revision:
        raise RuntimeError('HEAD differs from the build source_revision; rebuild from the release commit')
    expected = manifest.get('source_fingerprint')
    if compute_release_source_fingerprint(root) != expected or committed_fingerprint(root, revision) != expected:
        raise RuntimeError('Build inputs differ from committed source (including untracked/deleted inputs or line endings). Commit reviewed release inputs and rebuild.')
    return revision


def gh_json(endpoint, *, missing_ok=False):
    result = subprocess.run(
        ['gh', 'api', endpoint],
        capture_output=True,
        text=True,
        encoding='utf-8',
    )
    if result.returncode:
        if missing_ok and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError('GitHub API verification failed: ' + endpoint)
    return json.loads(result.stdout)


def verify_remote(repo, tag, revision, *, require_tag=False):
    commit = gh_json(f'repos/{repo}/commits/{revision}')
    if commit.get('sha') != revision:
        raise RuntimeError('Build commit is not available in the release repository')
    ref = gh_json(f'repos/{repo}/git/ref/tags/{tag}', missing_ok=True)
    if ref is None:
        if require_tag:
            raise RuntimeError('Release tag is missing')
    else:
        obj = ref['object']
        for _ in range(8):
            if obj['type'] != 'tag':
                break
            obj = gh_json(f'repos/{repo}/git/tags/{obj["sha"]}')['object']
        if obj['type'] != 'commit' or obj['sha'] != revision:
            raise RuntimeError('Existing tag points to different source; never move a published tag automatically')
    releases = gh_json(f'repos/{repo}/releases?per_page=1')
    if releases and releases[0]['tag_name'] != tag:
        date = datetime.fromisoformat(commit['commit']['committer']['date'].replace('Z', '+00:00'))
        first_date = datetime.fromisoformat(releases[0]['created_at'].replace('Z', '+00:00'))
        if date <= first_date:
            raise RuntimeError('Build commit predates the first release; source synchronization is required, not a synthetic timestamp')


def public_get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'NoahAI-release-verifier', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()


def verify_public(repo, tag, updater_version):
    api = f'https://api.github.com/repos/{repo}/releases'
    latest = json.loads(public_get(api + '/latest'))
    listing = json.loads(public_get(api + '?per_page=1'))
    feed = ET.fromstring(public_get(f'https://github.com/{repo}/releases.atom'))
    link = feed.find('{http://www.w3.org/2005/Atom}entry/{http://www.w3.org/2005/Atom}link')
    if (latest.get('tag_name') != tag or not listing or listing[0].get('tag_name') != tag
            or link is None or not link.get('href', '').endswith('/tag/' + tag)):
        raise RuntimeError('Release is published but public latest/list/Atom disagree; publication is NOT verified. Do not delete or retag to retry.')
    import yaml
    metadata = yaml.safe_load(public_get(f'https://github.com/{repo}/releases/download/{tag}/latest.yml'))
    installer = f'NoahAI-{tag.removeprefix("v")}-Setup.exe'
    assets = {item['name'] for item in latest.get('assets', [])}
    if (metadata.get('version') != updater_version or metadata.get('path') != installer
            or installer not in assets or installer + '.blockmap' not in assets):
        raise RuntimeError('Public Windows updater metadata/assets disagree')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest', default='deploy/release-manifest.json')
    parser.add_argument('--repo', default='nwsoft/ai-trading-client')
    parser.add_argument('--phase', choices=['preflight', 'tagged', 'published'], default='preflight')
    args = parser.parse_args()
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', args.repo):
        parser.error('Invalid repository')
    manifest = json.loads((args.root / args.manifest).read_text(encoding='utf-8'))
    if not re.fullmatch(r'\d+\.\d+\.\d+\.\d+', manifest['version']):
        parser.error('Invalid version')
    tag = 'v' + manifest['version']
    revision = verify_source(args.root, manifest)
    verify_remote(args.repo, tag, revision, require_tag=args.phase != 'preflight')
    if args.phase == 'published':
        verify_public(args.repo, tag, manifest['update_contract']['updater_semver'])
    print(revision)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f'RELEASE_PROVENANCE_BLOCKED: {exc}')
