import json
from pathlib import Path

from config.app_version import RELEASE_BUILD_LABEL, RELEASE_HIGHLIGHT, RELEASE_PATCH, RELEASE_VERSION


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_user_surfaces_share_provider_scope_and_menu_path():
    for relative in (
        "README.md",
        "RELEASE_NOTES.md",
        "docs/USER_GUIDE.md",
        "docs/AI_API_USER_GUIDE.md",
        "ui/widgets/user_manual_widget.py",
    ):
        source = _read(relative)
        assert "OpenAI" in source
        assert "DeepSeek" in source
        assert "Anthropic Claude" in source
        assert "Google Gemini" in source
        assert "Kimi K3" in source
        assert "AI 엔진/API" in source


def test_release_metadata_and_installed_manual_are_scoped_separately():
    readme = _read("README.md")
    assert f"현재 소스 후보: v{RELEASE_VERSION}" in readme
    assert RELEASE_PATCH in readme
    assert "Windows 검증 후보" in readme
    assert "모든 필수 행이 `[x] VERIFIED`" in readme
    assert "v3.9.0.5 설정 정본·실행 모드 통합" in _read("RELEASE_NOTES.md")
    manual = _read("ui/widgets/user_manual_widget.py")
    assert "현재 설치 버전" in manual
    assert f"v{RELEASE_VERSION} 최신 업데이트" in manual
    assert "새 Windows 빌드 전 업데이트 대상" not in manual
    assert "SHA-256이 게시된 Windows" in _read("docs/AI_API_USER_GUIDE.md")
    manifest_path = ROOT / "deploy" / "release-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_is_current = manifest["version"] == RELEASE_VERSION
        assert tuple(map(int, manifest["version"].split("."))) <= tuple(map(int, RELEASE_VERSION.split(".")))
        if manifest_is_current:
            assert manifest["release_label"] == RELEASE_BUILD_LABEL
        else:
            assert manifest["publish_ready"] is True
            assert f"공개 v{manifest['version']}" in _read("RELEASE_NOTES.md")
        assert manifest["build_status"] in {
            "pending_windows_rebuild",
            "built_windows_unverified",
            "windows_external_gates_pending",
            "windows_stable_external_gates_pending",
            "windows_verified_release_candidate",
        }
        if manifest["build_status"] == "pending_windows_rebuild":
            assert manifest["publish_ready"] is False
            assert manifest.get("source_fingerprint") is None
        else:
            assert len(manifest.get("source_fingerprint") or "") == 64
            assert manifest_is_current is False or manifest["previous_published_asset"]["version"] != RELEASE_VERSION
            assert manifest["previous_published_asset"]["path"].startswith("deploy/web-release/NoahAI-")
        assert manifest["previous_published_asset"]["purpose"] == "previous_published_windows_build"
    deployed_version = _read("deploy/version.txt").strip()
    assert tuple(map(int, deployed_version.split("."))) <= tuple(map(int, RELEASE_VERSION.split(".")))
    if manifest_path.exists():
        assert deployed_version == manifest["version"]
    assert f'RELEASE_VERSION = "{RELEASE_VERSION}"' in _read("config/app_version.py")
    assert f"FileVersion', u'{RELEASE_VERSION}" in _read("config/windows_version_info.txt")
    assert f"ProductVersion', u'{RELEASE_VERSION}" in _read("config/windows_version_info.txt")
    assert f'RELEASE_HIGHLIGHT = "{RELEASE_HIGHLIGHT}"' in _read("config/app_version.py")


def test_release_asset_generator_preserves_fix_patch_identity(tmp_path):
    from scripts.generate_release_assets import _build_manifest

    notes = tmp_path / "release_notes.md"
    notes.write_text("Fix Patch 3\n", encoding="utf-8")
    missing_exe = tmp_path / "AITrading.exe"
    pending = _build_manifest(
        version="3.9.0.8",
        release_label="v3.9.0.8 AI Custom Update Fix 2",
        exe_path=missing_exe,
        notes_path=notes,
        repo="nwsoft/ai-trading-client",
    )
    assert pending["release_label"] == "v3.9.0.8 AI Custom Update Fix 2"
    assert pending["build_status"] == "pending_windows_rebuild"

    missing_exe.write_bytes(b"windows-build")
    built = _build_manifest(
        version="3.9.0.8",
        release_label="v3.9.0.8 AI Custom Update Fix 2",
        exe_path=missing_exe,
        notes_path=notes,
        repo="nwsoft/ai-trading-client",
    )
    assert built["release_label"] == "v3.9.0.8 AI Custom Update Fix 2"
    assert built["build_status"] == "built"
    assert built["assets"]["exe"]["size"] == len(b"windows-build")
    assert built["assets"]["exe"]["sha256"]


def test_alpha_arena_scope_does_not_claim_deprecated_engine_is_current():
    guide = _read("docs/USER_GUIDE.md")
    whitepaper = _read("docs/NOAHAI_TECHNICAL_WHITEPAPER.md")
    assert "DeepSeek V4 Flash (현재 AlphaArena 단일 실행 기준)" in guide
    assert "DeepSeek 3.1 (현재 대시보드 실행 기준)" not in guide
    assert "승리 알고리즘" not in guide
    assert "일반 AI의 Claude·Gemini 선택과 AlphaArena 멀티 엔진 실거래는 별도 범위" in whitepaper


def test_manual_explains_hidden_tab_and_safe_update_behavior():
    manual = _read("ui/widgets/user_manual_widget.py")
    assert "숨겨진 거래소·증권사 상세 탭" in manual
    assert "화면 조회를 쉬게 해도 실제 자동매매 워커는 중지하지 않음" in manual
    assert "설정 → 업데이트" in manual
    assert "사용자 재개 전 신규 주문 잠금" in manual


def test_ai_architecture_is_router_first_not_legacy_openai_only():
    architecture = _read("docs/AI_API_ARCHITECTURE.md")
    assert "AIProviderRouter" in architecture
    assert "AnthropicClient" in architecture
    assert "로컬 credential 호환 계층" in architecture
    assert "Windows Credential Manager" not in architecture
    assert "ProviderCapabilities" in architecture
    assert "Phase 2: 하이브리드" not in architecture
    assert "[ ] DeepSeek API 지원" not in architecture

