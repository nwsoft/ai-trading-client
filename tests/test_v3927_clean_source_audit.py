import hashlib
import json

from scripts import active_source_audit as audit


def setup_archive(tmp_path, monkeypatch):
    root = tmp_path / 'client'
    (root / 'config').mkdir(parents=True)
    (root / 'config/source_quarantine_manifest.json').write_text(json.dumps({
        'quarantine_root': '../historical_archive',
        'artifacts': [{'path': 'old.py', 'sha256': hashlib.sha256(b'old').hexdigest()}],
    }))
    monkeypatch.setattr(audit, 'ROOT', root)
    return root, tmp_path / 'historical_archive'


def test_clean_checkout_does_not_require_another_machines_external_archive(tmp_path, monkeypatch):
    root, _ = setup_archive(tmp_path, monkeypatch)
    result = audit._validate_quarantine()
    assert result['archive_status'] == 'not_present_on_build_machine'
    assert result['failures'] == []
    # Archive absence never permits an obsolete source in the build tree.
    (root / 'ui').mkdir()
    (root / 'ui/dashboard_fix.py').write_text('pass')
    assert audit._forbidden_active_sources() == ['ui/dashboard_fix.py']


def test_present_archive_still_requires_all_recorded_artifacts(tmp_path, monkeypatch):
    _, archive = setup_archive(tmp_path, monkeypatch)
    archive.mkdir()
    assert audit._validate_quarantine()['failures'] == ['missing:old.py']


def test_present_archive_rejects_tampering(tmp_path, monkeypatch):
    _, archive = setup_archive(tmp_path, monkeypatch)
    archive.mkdir()
    (archive / 'old.py').write_bytes(b'changed')
    assert audit._validate_quarantine()['failures'] == ['hash_mismatch:old.py']


def test_present_archive_verifies_recorded_hash(tmp_path, monkeypatch):
    _, archive = setup_archive(tmp_path, monkeypatch)
    archive.mkdir()
    (archive / 'old.py').write_bytes(b'old')
    result = audit._validate_quarantine()
    assert result['archive_status'] == 'verified'
    assert result['failures'] == []
