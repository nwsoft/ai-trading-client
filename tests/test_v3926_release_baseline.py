import hashlib
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.restore_previous_release_asset import restore
from config.app_version import PUBLIC_RELEASE_VERSION


def fixture(root):
    payload=b'verified previous installer fixture'
    (root/'deploy').mkdir()
    installer={'name':f'NoahAI-{PUBLIC_RELEASE_VERSION}-Setup.exe','size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    (root/'deploy/release-manifest.json').write_text(json.dumps({'version':PUBLIC_RELEASE_VERSION,'assets':{'installer':installer}}))
    (root/'config').mkdir();(root/'config/published_release_baselines.json').write_text(json.dumps({'releases':{PUBLIC_RELEASE_VERSION:installer}}))
    return payload


def test_clean_build_downloads_and_reuses_verified_published_baseline(tmp_path):
    payload=fixture(tmp_path)
    with patch('urllib.request.urlopen',return_value=BytesIO(payload)) as read:
        result=restore(tmp_path);assert result['verified'] and not result['cached']
        assert read.call_args.args[0].full_url.endswith(f'/v{PUBLIC_RELEASE_VERSION}/NoahAI-{PUBLIC_RELEASE_VERSION}-Setup.exe')
    with patch('urllib.request.urlopen',side_effect=AssertionError('no new download')):
        assert restore(tmp_path)['cached']


def test_bad_download_hash_cannot_replace_baseline_or_leave_partial_file(tmp_path):
    payload=fixture(tmp_path)
    with patch('urllib.request.urlopen',return_value=BytesIO(b'x'*len(payload))),pytest.raises(RuntimeError,match='hash'):
        restore(tmp_path)
    assert not list((tmp_path/'deploy/web-release').iterdir())


def test_corrupt_existing_baseline_is_not_overwritten(tmp_path):
    fixture(tmp_path);folder=tmp_path/'deploy/web-release';folder.mkdir();file=folder/f'NoahAI-{PUBLIC_RELEASE_VERSION}-Setup.exe';file.write_bytes(b'bad')
    with patch('urllib.request.urlopen',side_effect=AssertionError('do not overwrite')),pytest.raises(RuntimeError,match='hash'):
        restore(tmp_path)
    assert file.read_bytes()==b'bad'


def test_unexpected_published_identity_is_rejected_before_network(tmp_path):
    fixture(tmp_path);path=tmp_path/'deploy/release-manifest.json';row=json.loads(path.read_text());row['assets']['installer']['name']='../../other.exe';path.write_text(json.dumps(row))
    with patch('urllib.request.urlopen',side_effect=AssertionError('no request')),pytest.raises(RuntimeError,match='identity'):
        restore(tmp_path)


def test_fresh_git_checkout_without_generated_manifest_uses_pinned_baseline(tmp_path):
    payload=fixture(tmp_path);(tmp_path/'deploy/release-manifest.json').unlink()
    with patch('urllib.request.urlopen',return_value=BytesIO(payload)):
        assert restore(tmp_path)['verified']
    assert not (tmp_path/'deploy/release-manifest.json').exists()


def test_fresh_worktree_seeds_only_verified_previous_public_manifest(tmp_path):
    payload=fixture(tmp_path)
    (tmp_path/'deploy/release-manifest.json').unlink()
    pin=tmp_path/'config/published_release_baselines.json';baseline=json.loads(pin.read_text())
    installer=baseline['releases'][PUBLIC_RELEASE_VERSION]
    manifest={'version':PUBLIC_RELEASE_VERSION,'assets':{'installer':dict(installer)}}
    content=json.dumps(manifest).encode()
    source=tmp_path/'config/published.json';source.write_bytes(content)
    installer.update(manifest_source_path='config/published.json',manifest_source_sha256=hashlib.sha256(content).hexdigest())
    pin.write_text(json.dumps(baseline))
    with patch('urllib.request.urlopen',return_value=BytesIO(payload)):
        assert restore(tmp_path)['verified']
    assert (tmp_path/'deploy/release-manifest.json').read_bytes()==content


def test_tampered_manifest_source_cannot_seed_a_clean_build(tmp_path):
    fixture(tmp_path);(tmp_path/'deploy/release-manifest.json').unlink()
    pin=tmp_path/'config/published_release_baselines.json';baseline=json.loads(pin.read_text())
    baseline['releases'][PUBLIC_RELEASE_VERSION].update(manifest_source_path='config/published.json',manifest_source_sha256='0'*64)
    pin.write_text(json.dumps(baseline));(tmp_path/'config/published.json').write_text('tampered')
    with patch('urllib.request.urlopen',side_effect=AssertionError('must not download')):
        with pytest.raises(RuntimeError,match='manifest source hash'):restore(tmp_path)
    assert not (tmp_path/'deploy/release-manifest.json').exists()
