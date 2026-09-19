import json
from pathlib import Path

from config.app_version import RELEASE_VERSION
from trading.declarative_strategy_engine import DeclarativeStrategyEngine
from trading.selection_policy import _scope_matches


ROOT = Path(__file__).resolve().parents[1]


def test_v3911_scope_aliases_and_v3912_canonical_scopes_match_runtime_targets():
    cases = (
        ("exchange:unified", "crypto", "bybit", True),
        ("exchange:unified", "crypto", "okx", True),
        ("broker:connected", "stock", "kiwoom", True),
        ("broker:connected", "stock", "kis", True),
        ("asset:crypto", "crypto", "bitget", True),
        ("asset:stock", "stock", "shinhan", True),
        ("exchange:binance", "crypto", "bybit", False),
        ("broker:connected", "crypto", "binance", False),
    )
    for scope, asset_class, target, expected in cases:
        assert _scope_matches(scope, asset_class=asset_class, target=target) is expected
        assert DeclarativeStrategyEngine._scope_matches(
            scope, asset_class=asset_class, target=target
        ) is expected


def test_strategy_studio_exposes_reset_reanalysis_save_reason_and_real_xai_levels():
    source = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    for marker in (
        "target_scope: executionTarget",
        "defaultExecutionTarget(service, source)",
        "새로 시작 · 입력 초기화",
        "입력 중인 초안만 초기화했습니다",
        "먼저 AI 분석 및 전략 초안 만들기를 실행하세요",
        "12단계 자세히 · API 비용 없음",
        "자료 분석 범위",
        "엔진 적용값",
        "원문-규칙 추적",
        "Noah Strategy IR 전체",
        "Documents/NoahAI/<계정>/custom_strategies",
        "무자막 음성 전사는 기본 최대 45분이면서 24MB 이하",
    ):
        assert marker in source

    # 새 URL/텍스트가 이전 파일보다 우선되도록 세 입력 경로 모두 분석을 폐기한다.
    assert source.count("setSourceFile(null)") >= 5
    assert source.count("setSourceAnalysis(null)") >= 7


def test_current_release_is_pending_until_new_windows_assets_exist():
    manifest = json.loads((ROOT / "deploy" / "release-manifest.json").read_text(encoding="utf-8"))
    package = json.loads((ROOT / "webui" / "package.json").read_text(encoding="utf-8"))
    major, minor, patch, revision = (int(part) for part in RELEASE_VERSION.split("."))
    updater_version = f"{major}.{minor}.{patch * 100 + revision}"

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
    assert manifest["assets"]["installer"]["name"] == f"NoahAI-{manifest['version']}-Setup.exe"
    if manifest["build_status"] == "pending_windows_rebuild":
        assert manifest["assets"]["installer"]["sha256"] == ""
    else:
        assert manifest["assets"]["installer"]["sha256"]
    assert manifest_is_current is False or manifest["previous_published_asset"]["version"] != RELEASE_VERSION
    assert package["version"] == updater_version
    assert package["build"]["buildVersion"] == RELEASE_VERSION
