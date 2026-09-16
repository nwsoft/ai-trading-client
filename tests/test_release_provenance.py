import json
import subprocess

import pytest

from scripts import verify_release_provenance as verifier
from scripts.release_source_fingerprint import compute_release_source_fingerprint


@pytest.fixture
def source_repo(tmp_path):
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args]).decode().strip()
    git('init', '-q')
    git('config', 'user.name', 'Release Test')
    git('config', 'user.email', 'release-test@example.invalid')
    git('config', 'core.autocrlf', 'false')
    # Use exact LF bytes so the CRLF mutation below remains meaningful on Windows.
    (tmp_path / 'app.py').write_bytes(b'print("release")\n')
    (tmp_path / 'old.py').write_bytes(b'old = True\n')
    git('add', 'app.py', 'old.py')
    git('commit', '-qm', 'fixture')
    manifest = {'source_revision': git('rev-parse', 'HEAD'),
                'source_fingerprint': compute_release_source_fingerprint(tmp_path)}
    return tmp_path, manifest


def test_exact_committed_source_passes(source_repo):
    root, manifest = source_repo
    assert verifier.verify_source(root, manifest) == manifest['source_revision']


@pytest.mark.parametrize('change', ['modified', 'untracked', 'deleted', 'eol'])
def test_dirty_build_cannot_claim_old_head_even_with_fresh_manifest(source_repo, change):
    root, manifest = source_repo
    if change == 'modified':
        (root / 'app.py').write_text('new = True\n')
    elif change == 'untracked':
        (root / 'new.py').write_text('new = True\n')
    elif change == 'deleted':
        (root / 'old.py').unlink()
    else:
        (root / 'app.py').write_bytes(b'print("release")\r\n')
    manifest['source_fingerprint'] = compute_release_source_fingerprint(root)
    with pytest.raises(RuntimeError, match='Build inputs differ'):
        verifier.verify_source(root, manifest)


def test_generated_artifact_does_not_make_source_dirty(source_repo):
    root, manifest = source_repo
    (root / 'installer.exe').write_bytes(b'generated fixture')
    assert verifier.verify_source(root, manifest)


def test_no_git_or_missing_revision_is_blocked(tmp_path):
    with pytest.raises(RuntimeError, match='source_revision is required'):
        verifier.verify_source(tmp_path, {'source_revision': 'unavailable'})


def remote(monkeypatch, *, tag_sha=None, date='2026-09-17T00:00:00Z', annotated=False):
    revision = 'a' * 40
    def api(endpoint, **kwargs):
        if '/commits/' in endpoint:
            return {'sha': revision, 'commit': {'committer': {'date': date}}}
        if '/git/ref/' in endpoint:
            return None if tag_sha is None else {'object': {'type': 'tag' if annotated else 'commit', 'sha': tag_sha}}
        if '/git/tags/' in endpoint:
            return {'object': {'type': 'commit', 'sha': revision}}
        return [{'tag_name': 'v3.9.0.10', 'created_at': '2026-08-13T15:10:07Z'}]
    monkeypatch.setattr(verifier, 'gh_json', api)
    return revision


def test_old_main_commit_is_blocked_before_tag_creation(monkeypatch):
    revision = remote(monkeypatch, date='2025-05-01T18:33:47Z')
    with pytest.raises(RuntimeError, match='predates'):
        verifier.verify_remote('owner/repo', 'v3.9.1.37', revision)


def test_fresh_commit_and_annotated_tag_are_supported(monkeypatch):
    revision = remote(monkeypatch)
    verifier.verify_remote('owner/repo', 'v3.9.1.37', revision)
    revision = remote(monkeypatch, tag_sha='b' * 40, annotated=True)
    verifier.verify_remote('owner/repo', 'v3.9.1.37', revision, require_tag=True)


def test_conflicting_or_missing_tag_never_retargeted(monkeypatch):
    revision = remote(monkeypatch, tag_sha='b' * 40)
    with pytest.raises(RuntimeError, match='never move'):
        verifier.verify_remote('owner/repo', 'v3.9.1.37', revision)
    remote(monkeypatch)
    with pytest.raises(RuntimeError, match='tag is missing'):
        verifier.verify_remote('owner/repo', 'v3.9.1.37', revision, require_tag=True)


@pytest.mark.parametrize('wrong', ['', 'latest', 'list', 'atom', 'metadata'])
def test_public_ordering_and_metadata_must_all_match(monkeypatch, wrong):
    tag = 'v3.9.1.37'
    def get(url):
        if url.endswith('/latest'):
            return json.dumps({'tag_name': 'old' if wrong == 'latest' else tag,
                               'assets': [{'name': 'NoahAI-3.9.1.37-Setup.exe'}, {'name': 'NoahAI-3.9.1.37-Setup.exe.blockmap'}]}).encode()
        if '?per_page=1' in url:
            return json.dumps([{'tag_name': 'old' if wrong == 'list' else tag}]).encode()
        if url.endswith('.atom'):
            selected = 'old' if wrong == 'atom' else tag
            return f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link href="https://github.com/owner/repo/releases/tag/{selected}"/></entry></feed>'.encode()
        version = '3.9.136' if wrong == 'metadata' else '3.9.137'
        return f'version: {version}\npath: NoahAI-3.9.1.37-Setup.exe\n'.encode()
    monkeypatch.setattr(verifier, 'public_get', get)
    if wrong:
        with pytest.raises(RuntimeError):
            verifier.verify_public('owner/repo', tag, '3.9.137')
    else:
        verifier.verify_public('owner/repo', tag, '3.9.137')


def test_publishers_require_explicit_verified_target():
    root = verifier.ROOT
    windows = (root / 'scripts/publish_web_ui_windows_release.ps1').read_text()
    mac = (root / 'scripts/publish_macos.py').read_text()
    assert '--target $releaseTarget' in windows
    assert windows.index('--phase preflight') < windows.index('gh release create')
    assert windows.index('git push origin $tagRefSpec') < windows.index('--phase tagged')
    assert windows.index('--phase tagged') < windows.index('gh release upload')
    assert '--phase published' in windows
    assert '"--target", release_target' in mac
    assert 'verify_source(ROOT, manifest)' in mac
