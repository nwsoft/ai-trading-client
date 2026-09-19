import json
from pathlib import Path
import subprocess

from config.app_version import RELEASE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_v3915_is_a_new_blocked_candidate_not_a_same_version_replacement():
    package = json.loads(_read("webui/package.json"))
    manifest = json.loads(_read("deploy/release-manifest.json"))
    major, minor, patch, revision = (int(part) for part in RELEASE_VERSION.split("."))
    updater_version = f"{major}.{minor}.{patch * 100 + revision}"

    assert package["version"] == updater_version
    assert package["build"]["buildVersion"] == RELEASE_VERSION
    assert package["build"]["win"]["artifactName"] == f"NoahAI-{RELEASE_VERSION}-Setup.${{ext}}"
    manifest_is_current = manifest["version"] == RELEASE_VERSION
    assert tuple(map(int, manifest["version"].split("."))) <= tuple(map(int, RELEASE_VERSION.split(".")))
    assert manifest["build_status"] in {
        "pending_windows_rebuild",
        "built_windows_unverified",
        "windows_external_gates_pending",
        "windows_stable_external_gates_pending",
        "windows_verified_release_candidate",
    }
    assert manifest["publish_ready"] in {False, True}
    if manifest["build_status"] == "pending_windows_rebuild":
        assert manifest["assets"]["installer"]["sha256"] == ""
    else:
        assert manifest["assets"]["installer"]["sha256"]
    assert manifest_is_current is False or manifest["previous_published_asset"]["version"] != RELEASE_VERSION


def test_electron_losing_instance_cannot_register_engine_startup_and_metadata_wins():
    source = _read("webui/electron/main.cjs")
    lock_index = source.index("const ownsSingleInstanceLock = app.requestSingleInstanceLock()")
    losing_index = source.index("if (!ownsSingleInstanceLock)", lock_index)
    owner_index = source.index("} else {", losing_index)
    ready_index = source.index("app.whenReady().then", owner_index)

    assert losing_index < owner_index < ready_index
    assert "second NoahAIEngine.exe" in source
    helper = _read("webui/electron/version.cjs")
    assert helper.index("info?.version") < helper.index("info?.releaseName")
    assert "latest.yml is the updater contract" in helper
    major, minor, patch, revision = (int(part) for part in RELEASE_VERSION.split("."))
    updater_version = f"{major}.{minor}.{patch * 100 + revision}"
    result = subprocess.run(
        [
            "node",
            "-e",
            "const {displayVersion}=require('./webui/electron/version.cjs');"
            f"process.stdout.write(displayVersion({{version:'{updater_version}',releaseName:'v3.9.0.10'}}));",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout == RELEASE_VERSION
    package_result = subprocess.run(
        [
            "node",
            "-e",
            "const {packageProductVersion}=require('./webui/electron/version.cjs');"
            "process.stdout.write(packageProductVersion({version:'3.9.128',build:{buildVersion:'3.9.1.28'}},'43.4.0'));",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert package_result.stdout == "3.9.1.28"


def test_settings_failure_receipt_and_windows_lock_are_user_support_visible():
    settings = _read("config/settings.py")
    services = _read("web_platform/application_services.py")
    api = _read("webui/src/api.ts")

    for marker in (
        "_settings_interprocess_lock",
        "SettingsLockTimeoutError",
        "concurrent_writer_timeout",
        "file_locked",
        "replace_canonical",
        "winerror",
    ):
        assert marker in settings
    assert 'self._audit("settings.write_failed", details)' in services
    assert "설정 저장 실패 — " in services
    assert "지원 코드: file_locked" in api
    assert "지원 코드: concurrent_writer_timeout" in api


def test_settings_footer_prevents_button_glyph_wrapping_at_fixed_modal_width():
    css = _read("webui/src/styles.css")

    assert '"Malgun Gothic"' in css
    compact_button = css[css.index(".settings-center button {"):]
    compact_button = compact_button.split("}", 1)[0]
    assert "font-size: 10px" in compact_button
    assert "line-height: 1.2" in compact_button
    assert ".settings-center > footer > div { flex: 0 0 auto; flex-wrap: nowrap; }" in css
    footer_button = css[css.index(".settings-center > footer button {"):]
    assert "white-space: nowrap" in footer_button.split("}", 1)[0]
    footer_message = css[css.index(".settings-center > footer > span {"):]
    assert "flex: 1 1 auto" in footer_message.split("}", 1)[0]


def test_settings_center_uses_compact_save_layout_and_write_only_presence_status():
    component = _read("webui/src/components/SettingsCenter.tsx")
    css = _read("webui/src/styles.css")
    services = _read("web_platform/application_services.py")

    assert 'className="settings-command-actions"' in component
    assert 'className="settings-command-save-row"' in component
    assert 'className="credential-status-list"' in component
    assert 'className="credential-input-grid"' in component
    assert "•••••••• 저장됨" in component
    assert "저장된 키로 실제 연결 점검" in component
    assert 'className="settings-preset-row settings-ai-action-row"' in component
    assert ".settings-command-save-row { grid-column: 1 / -1;" in css
    assert ".settings-ai-action-row { flex-wrap: nowrap;" in css
    assert '"credential_field_status": self._credential_field_status(settings)' in services
    assert "Return per-field presence without returning any credential value." in services


def test_settings_center_labels_technical_crypto_controls_as_advanced_rules():
    component = _read("webui/src/components/SettingsCenter.tsx")
    services = _read("web_platform/application_services.py")
    analyzer = _read("trading/analyzer.py")
    manual = _read("ui/widgets/user_manual_widget.py")

    assert "코인 선물 마진 방식" in services
    assert '"ai_learning_min_samples": "실제 완료 거래 표본과 연결되지 않은 레거시 값' in services
    assert "ai_analysis.get('samples_count'" not in analyzer
    assert "코인 신호 기준 자동 보정" in services
    assert "생성형 AI가 수익 규칙을 스스로 만드는 기능이 아닙니다" in component
    assert "코인 시장상태 자동 보정 (규칙 기반)" in component
    assert "기본 자율운행 · 시작 전에 3가지만 확인하세요" in component
    assert "거래 데이터 0건부터 실행 가능" in component
    assert "매뉴얼에서 자세히 보기" in component
    assert "기본 자율운행을 가장 짧게 이해하기" in manual
    assert "20번 학습하거나 20번 거래해야 첫 주문 후보를 만드는 절차는 없습니다" in manual


def test_publish_script_requires_the_current_unfinished_windows_plan():
    publish = _read("scripts/publish_web_ui_windows_release.ps1")
    plan_prefix = "V" + RELEASE_VERSION.replace(".", "")
    plan_matches = sorted((ROOT / "docs").glob(f"{plan_prefix}*_TEST_PLAN.md"))
    assert len(plan_matches) == 1
    plan = plan_matches[0].read_text(encoding="utf-8")

    assert "Get-PatchPlanPath" in publish
    assert "Assert-PatchPlanComplete" in publish
    assert "AllowPendingExternalGates" in publish
    assert "V*_TEST_PLAN.md" in publish
    assert 'if ($version -eq "3.9.1.7")' not in publish
    for gate in (
        "WIN-BUILD",
        "WIN-UPGRADE",
        "KIWOOM-E2E",
        "KIS-E2E",
        "BITHUMB-E2E",
        "RECONCILE-E2E",
        "SPOT-FUTURES-PAPER",
        "REPORT-E2E",
        "SOAK",
    ):
        assert gate in plan
    assert "- [ ]" in plan
