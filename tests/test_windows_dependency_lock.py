from importlib.metadata import PackageNotFoundError
import importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lock_check', ROOT / 'scripts/verify_windows_dependencies.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def test_version_drift_and_missing_package_fail(tmp_path):
    lock = tmp_path / 'lock.txt'
    lock.write_text('example==1.2.3\nmissing==4.5.6\n')
    def lookup(name):
        if name == 'missing':
            raise PackageNotFoundError(name)
        return '1.2.4'
    errors = module.mismatches(lock, lookup)
    assert len(errors) == 2
    assert 'actual 1.2.4' in errors[0]
    assert 'actual missing' in errors[1]

def test_direct_requirements_match_recorded_pins():
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import Version
    for target in ['windows', 'kiwoom_x86']:
        lock = ROOT / f'requirements_{target}.lock.txt'
        pins = dict(line.split('==') for line in lock.read_text().splitlines() if line and not line.startswith('#'))
        normalized = {canonicalize_name(k): v for k, v in pins.items()}
        assert module.mismatches(lock, pins.__getitem__) == []
        for line in (ROOT / f'requirements_{target}.txt').read_text().splitlines():
            if not line or line.startswith(('#', '-')):
                continue
            req = Requirement(line)
            assert Version(normalized[canonicalize_name(req.name)]) in req.specifier

def test_old_sidecars_blocked_and_staging_cleared():
    build = (ROOT / 'scripts/build_web_ui_windows.ps1').read_text()
    assert 'if ($SkipEngineBuild) { throw' in build
    assert build.index('Remove-Item -LiteralPath "dist\\NoahAIEngine.exe"') < build.index('Build Python engine sidecar')
    assert build.index('Get-ChildItem -LiteralPath $engineDir -Force | Remove-Item') < build.index('Copy-Item -LiteralPath $engineSource')
    assert 'Verify locked Windows dependencies' in build
    assert 'Verify locked Kiwoom dependencies' in build
