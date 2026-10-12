"""Acceptance evidence must describe the same gates that are counted."""
import json
import os
import shutil
import subprocess
from pathlib import Path
import pytest
from scripts.release_acceptance import read_plan
from config.app_version import RELEASE_VERSION

ROOT = Path(__file__).resolve().parents[1]


def write_plan(root, rows, version='3.9.2.13'):
    path = root / 'docs/DEPLOY_CHECKLIST.md'
    path.parent.mkdir(exist_ok=True)
    path.write_text(f'<!-- patch-test-plan-version: {version} -->\n{rows}\n<!-- patch-test-plan-end -->\n', encoding='utf-8')


def test_original_nine_are_actual_release_checklist_rows():
    snapshot = read_plan(ROOT, '3.9.2.12')
    assert snapshot['pending_ids'] == ['SDK','WIN-BUILD','WIN-UPGRADE','UPLOAD','REPLAY-COST','CATALOG','ROLLBACK','SOAK','PUBLISH']
    assert snapshot['pending_count'] == 9
    # Historical rows remain unchanged after publication; they are a snapshot.
    assert snapshot['scope'] == 'release_checklist_snapshot'


def test_current_count_ids_and_status_are_one_snapshot(tmp_path):
    write_plan(tmp_path, '- [x] WIN-BUILD: built evidence\n- [ ] ROLLBACK: tester pending\n- [ ] SOAK: tester pending')
    result = read_plan(tmp_path, '3.9.2.13')
    assert result['pending_ids'] == ['ROLLBACK','SOAK']
    assert result['pending_count'] == 2
    assert result['items'][0]['status'] == 'complete'
    write_plan(tmp_path, '- [x] WIN-BUILD: built evidence\n- [x] ROLLBACK: restored evidence')
    result = read_plan(tmp_path, '3.9.2.13')
    assert result['status'] == 'complete'
    assert result['pending_ids'] == []
    assert result['pending_count'] == 0


@pytest.mark.parametrize('rows', [
    '- [ ] WIN-BUILD: a\n- [ ] ROLLBACK: b\n- [x] ROLLBACK: duplicate',
    '- [ ] WIN-BUILD: a\n- [ ] ROLLBACK missing colon',
    '- [ ] WIN-BUILD: a',
    '- [ ] WIN-BUILD: a\n- [!] ROLLBACK: invalid',
])
def test_invalid_plan_cannot_silently_report_complete(tmp_path, rows):
    write_plan(tmp_path, rows)
    with pytest.raises(ValueError): read_plan(tmp_path, '3.9.2.13')


def test_missing_or_duplicate_version_markers_and_end_fail(tmp_path):
    write_plan(tmp_path, '- [x] WIN-BUILD: a\n- [x] ROLLBACK: b')
    path = tmp_path / 'docs/DEPLOY_CHECKLIST.md'
    text = path.read_text()
    with pytest.raises(ValueError): read_plan(tmp_path, '3.9.2.12')
    for invalid in (text + text, text.replace('<!-- patch-test-plan-end -->', '')):
        path.write_text(invalid)
        with pytest.raises(ValueError): read_plan(tmp_path, '3.9.2.13')


def test_cli_current_plan_matches_build_and_publisher_contract():
    result = subprocess.run([os.sys.executable, str(ROOT/'scripts/release_acceptance.py'), '--version', RELEASE_VERSION], capture_output=True, text=True, check=True)
    snapshot = json.loads(result.stdout)
    assert snapshot['pending_count'] == len(snapshot['pending_ids'])
    assert {r['id'] for r in snapshot['items'] if r['status']=='pending'} == set(snapshot['pending_ids'])
    build=(ROOT/'scripts/build_web_ui_windows.ps1').read_text()
    publish=(ROOT/'scripts/publish_web_ui_windows_release.ps1').read_text()
    assert 'scripts/release_acceptance.py' in build and 'scripts/release_acceptance.py' in publish
    assert 'external_validation = @($acceptance.pending_ids)' in build
    assert 'external_validation_items = @($acceptance.items)' in build
    assert 'external_validation -NotePropertyValue @($planStatus.pending_ids)' in publish
    assert 'external_validation_items -NotePropertyValue @($planStatus.items)' in publish


def test_powershell_publisher_reads_real_snapshot_without_publishing(tmp_path):
    shell = shutil.which('pwsh') or shutil.which('powershell')
    if not shell:
        pytest.skip('PowerShell is required for the pure release-plan wrapper test')
    # Parse only pure functions from the publisher. Never dot-source its release actions.
    script = tmp_path/'plan-wrapper.ps1'
    def quote(value): return "'" + str(value).replace("'", "''") + "'"
    script.write_text('''$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile('''+quote(ROOT/'scripts/publish_web_ui_windows_release.ps1')+''', [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Publisher syntax error' }
foreach ($name in @('Get-PatchPlanPath','Get-PatchPlanStatus')) {
    $function=$ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq $name},$true)[0]
    Invoke-Expression $function.Extent.Text
}
Get-PatchPlanStatus '''+quote(ROOT)+' '+quote(RELEASE_VERSION)+''' | ConvertTo-Json -Depth 8 -Compress
''', encoding='utf-8-sig')
    env=dict(os.environ)
    env['PATH']=str(Path(os.sys.executable).parent)+os.pathsep+env.get('PATH','')
    env['PYTHONUTF8']='1'
    result=subprocess.run([shell,'-NoProfile','-File',str(script)],capture_output=True,text=True,encoding='utf-8',env=env,check=True)
    assert json.loads(result.stdout) == read_plan(ROOT,RELEASE_VERSION)


def test_cli_survives_windows_legacy_console_encoding():
    env=dict(os.environ, PYTHONIOENCODING='ascii', PYTHONUTF8='0')
    result=subprocess.run([os.sys.executable,str(ROOT/'scripts/release_acceptance.py'),'--version',RELEASE_VERSION],env=env,capture_output=True,check=True)
    assert json.loads(result.stdout.decode('ascii')) == read_plan(ROOT,RELEASE_VERSION)


@pytest.mark.parametrize('relative', ['scripts/release_acceptance.py','docs/DEPLOY_CHECKLIST.md'])
def test_acceptance_input_changes_invalidate_release_fingerprint(tmp_path, relative):
    from scripts.release_source_fingerprint import compute_release_source_fingerprint
    path=tmp_path/relative;path.parent.mkdir(parents=True)
    path.write_bytes(b'original\n')
    before=compute_release_source_fingerprint(tmp_path)
    path.write_bytes(b'changed\n')
    assert compute_release_source_fingerprint(tmp_path) != before
