"""Additional QA for the already-published .12 source; no product policy change."""
import json
import subprocess
from pathlib import Path
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

@pytest.mark.parametrize("autocrlf", ["false", "true"])
def test_hash_pinned_manifest_keeps_original_bytes_in_fresh_checkout(source_repo, tmp_path, autocrlf):
    """Published archives must retain their digest across commit and OS checkout."""
    root, _ = source_repo
    (root / ".gitattributes").write_bytes((verifier.ROOT / ".gitattributes").read_bytes())
    relative = "config/published_release_manifests/v3.9.2.11.json"
    archive = root / relative
    archive.parent.mkdir(parents=True)
    raw = b'{"version":"3.9.2.11","fixture":true}\r\n'
    archive.write_bytes(raw)
    def git(*args):
        return subprocess.check_output(["git", "-C", str(root), *args])
    git("add", ".gitattributes", relative)
    git("commit", "-qm", "preserve hash-pinned archive")
    assert git("show", "HEAD:" + relative) == raw
    checkout = tmp_path / ("restored-" + autocrlf)
    subprocess.run(["git", "clone", "-q", "-c", "core.autocrlf=" + autocrlf,
                    str(root), str(checkout)], check=True)
    assert (checkout / relative).read_bytes() == raw
    manifest = {"source_revision": git("rev-parse", "HEAD").decode().strip(),
                "source_fingerprint": compute_release_source_fingerprint(root)}
    assert verifier.verify_source(checkout, manifest) == manifest["source_revision"]

def test_exported_paper_help_stays_byte_identical_with_windows_default_newlines(tmp_path, monkeypatch):
    """Build exports must not alter release inputs on Windows before provenance."""
    import runpy
    import sys
    root = Path(__file__).resolve().parents[1]
    script = tmp_path / "scripts/export_legacy_manual_sections.py"
    script.parent.mkdir()
    script.write_bytes((root / "scripts/export_legacy_manual_sections.py").read_bytes())
    manual = tmp_path / "ui/widgets/user_manual_widget.py"
    manual.parent.mkdir(parents=True)
    manual.write_bytes((root / "ui/widgets/user_manual_widget.py").read_bytes())
    (tmp_path / "docs").mkdir()
    original_write = Path.write_text
    def windows_write(path, data, *args, **kwargs):
        if kwargs.get("newline") is None:
            kwargs["newline"] = "\r\n"
        return original_write(path, data, *args, **kwargs)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(Path, "write_text", windows_write)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(script), run_name="__main__")
    assert stopped.value.code == 0
    relative = "webui/src/generated/paper-recovery-guide.json"
    assert (tmp_path / relative).read_bytes() == (root / relative).read_bytes()
    assert (tmp_path / "docs/USER_MANUAL_SECTIONS.json").read_bytes() == (root / "docs/USER_MANUAL_SECTIONS.json").read_bytes()
