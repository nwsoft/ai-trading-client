import hashlib
from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from scripts.restore_previous_release_asset import restore


def fixture(root):
    payload=b'verified previous installer fixture'
    (root/'deploy').mkdir()
    installer={'name':'NoahAI-3.9.2.5-Setup.exe','size':len(payload),'sha256':hashlib.sha256(payload).hexdigest()}
    (root/'deploy/release-manifest.json').write_text(json.dumps({'version':'3.9.2.5','assets':{'installer':installer}}))
    (root/'config').mkdir();(root/'config/published_release_baselines.json').write_text(json.dumps({'releases':{'3.9.2.5':installer}}))
    return payload


def test_clean_build_downloads_and_reuses_verified_published_baseline(tmp_path):
    payload=fixture(tmp_path)
    with patch('urllib.request.urlopen',return_value=BytesIO(payload)) as read:
        result=restore(tmp_path);assert result['verified'] and not result['cached']
        assert read.call_args.args[0].full_url.endswith('/v3.9.2.5/NoahAI-3.9.2.5-Setup.exe')
    with patch('urllib.request.urlopen',side_effect=AssertionError('no new download')):
        assert restore(tmp_path)['cached']


def test_bad_download_hash_cannot_replace_baseline_or_leave_partial_file(tmp_path):
    payload=fixture(tmp_path)
    with patch('urllib.request.urlopen',return_value=BytesIO(b'x'*len(payload))),pytest.raises(RuntimeError,match='hash'):
        restore(tmp_path)
    assert not list((tmp_path/'deploy/web-release').iterdir())


def test_corrupt_existing_baseline_is_not_overwritten(tmp_path):
    fixture(tmp_path);folder=tmp_path/'deploy/web-release';folder.mkdir();file=folder/'NoahAI-3.9.2.5-Setup.exe';file.write_bytes(b'bad')
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
