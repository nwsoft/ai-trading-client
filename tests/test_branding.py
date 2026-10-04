import json
from pathlib import Path
import shutil
import sys

import pytest

from scripts import verify_branding as branding
from scripts.release_source_fingerprint import compute_release_source_fingerprint, release_source_files

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def assets(tmp_path):
    for relative in (*branding.CANONICAL_HASHES, 'webui/package.json'):
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    return tmp_path


def test_tracked_noahai_images_decode_and_config_resolves(assets):
    assert branding.verify_assets(assets) == branding.CANONICAL_HASHES
    assert len(branding.ico_payloads((assets / 'icon.ico').read_bytes())) == 7


@pytest.mark.parametrize('relative', branding.CANONICAL_HASHES)
@pytest.mark.parametrize('change', ['missing', 'invalid', 'different_image'])
def test_missing_invalid_or_substitute_branding_fails(assets, relative, change):
    path = assets / relative
    if change == 'missing':
        path.unlink()
    elif change == 'invalid':
        path.write_bytes(b'not an image')
    else:
        from PIL import Image
        Image.new('RGB', (256, 256), 'blue').save(path)
    with pytest.raises(ValueError, match='branding asset|approved NoahAI'):
        branding.verify_assets(assets)


@pytest.mark.parametrize('section,key', [('win', 'icon'), ('mac', 'icon'), ('nsis', 'installerIcon'), ('nsis', 'uninstallerIcon')])
def test_ignored_build_path_is_rejected(assets, section, key):
    path = assets / 'webui/package.json'
    package = json.loads(path.read_text())
    package['build'][section][key] = 'build/icon.ico'
    path.write_text(json.dumps(package))
    with pytest.raises(ValueError, match='tracked branding'):
        branding.verify_assets(assets)


@pytest.mark.parametrize('data', [b'', b'\x00\x00\x01\x00\x01\x00', b'bad directory'])
def test_truncated_ico_cannot_pass(data):
    with pytest.raises(ValueError, match='Invalid ICO'):
        branding.ico_payloads(data)


def test_pe_icon_payloads_must_match_primary_group(monkeypatch, tmp_path):
    exe = tmp_path / 'NoahAI.exe'
    exe.write_bytes(b'executable fixture')
    expected = branding.ico_payloads((ROOT / 'icon.ico').read_bytes())
    monkeypatch.setattr(branding, 'pe_icon_groups', lambda path: [(1, 1033, list(reversed(expected)))])
    assert branding.verify_executable(exe, ROOT / 'icon.ico')['image_count'] == 7
    for groups in ([], [(1, 1033, [b'Electron default'])], [(1, 1033, expected[:-1])],
                   [(1, 1033, [b'default']), (2, 1033, expected)]):
        monkeypatch.setattr(branding, 'pe_icon_groups', lambda path, groups=groups: groups)
        with pytest.raises(ValueError, match='Primary PE icon'):
            branding.verify_executable(exe, ROOT / 'icon.ico')


@pytest.mark.skipif(sys.platform != 'win32', reason='Real Windows Python PE resource regression')
def test_real_non_noahai_executable_is_rejected():
    with pytest.raises(ValueError, match='Primary PE icon'):
        branding.verify_executable(Path(sys.executable), ROOT / 'icon.ico')


@pytest.mark.parametrize('relative', (*branding.CANONICAL_HASHES, 'scripts/verify_branding.py', 'webui/electron/branding-preflight.cjs'))
def test_branding_assets_and_verifier_change_fingerprint(tmp_path, relative):
    inputs = {path.relative_to(ROOT).as_posix() for path in release_source_files(ROOT)}
    assert relative in inputs
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b'first input')
    first = compute_release_source_fingerprint(tmp_path)
    path.write_bytes(b'changed input')
    assert first != compute_release_source_fingerprint(tmp_path)
