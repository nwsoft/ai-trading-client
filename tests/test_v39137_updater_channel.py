import subprocess
from pathlib import Path


def test_real_electron_updater_provider_with_stale_feed():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ['node', '--test', 'tests/updater-channel.test.cjs'],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )


def test_windows_build_installs_provider_before_python_regression():
    root = Path(__file__).resolve().parents[1]
    source = (root / 'scripts/build_web_ui_windows.ps1').read_text()
    assert source.index('Install locked Web dependencies') < source.index('Python full regression')


def test_manual_boundary_is_independent_of_mutable_release_manifest(tmp_path, monkeypatch):
    from scripts import export_legacy_manual_sections as exporter
    (tmp_path / 'deploy').mkdir()
    manifest = tmp_path / 'deploy/release-manifest.json'
    manifest.write_text('{"version":"3.9.1.36","publish_ready":true}')
    monkeypatch.setattr(exporter, 'ROOT', tmp_path)
    first = exporter._render_release_boundary('custom', 'guide')
    manifest.write_text('{"version":"9.9.9.9","publish_ready":false}')
    second = exporter._render_release_boundary('custom', 'guide')
    assert first == second
    assert 'v3.9.1.38 Windows stable/latest 공개 제품' in second
