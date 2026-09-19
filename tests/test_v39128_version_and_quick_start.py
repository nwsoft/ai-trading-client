import json
from pathlib import Path

from config.app_version import RELEASE_DISPLAY_LABEL, RELEASE_VERSION
from scripts.export_legacy_manual_sections import build_snapshot
from trading.exchanges.venue_capabilities import public_venue_registry


ROOT = Path(__file__).resolve().parents[1]


def test_user_visible_product_identity_does_not_expose_runtime_or_ui_implementation():
    app = (ROOT / "webui/src/App.tsx").read_text(encoding="utf-8")
    electron = (ROOT / "webui/electron/main.cjs").read_text(encoding="utf-8")

    package = json.loads((ROOT / "webui/package.json").read_text(encoding="utf-8"))
    assert RELEASE_VERSION == package['build']['buildVersion']
    assert RELEASE_DISPLAY_LABEL == f"v{RELEASE_VERSION}"
    assert "대시보드 Beta v${displayVersion}" in app
    assert "대시보드 Beta v${currentProductVersion()}" in electron
    assert "대시보드 Beta ${productVersion(app.getVersion())} Web UI" not in electron


def test_settings_quick_start_is_paper_first_and_keeps_explicit_save_boundary():
    settings = (ROOT / "webui/src/components/SettingsCenter.tsx").read_text(encoding="utf-8")

    for marker in (
        "처음 사용 · 빠른 시작",
        "외부 AI 호출 없이 한 질문씩",
        'paper_trading: true',
        'trade_enabled_exchanges: []',
        '"position_sizing_policy.mode": "account_risk"',
        "enabled_stock_brokers",
        '"stock_order_guardrails.enabled"',
        "아직 적용되지 않았습니다",
        "전체 설정 저장",
        "대시보드에서 해당 서비스를 직접 시작",
    ):
        assert marker in settings


def test_changelog_starts_with_current_candidate_and_preserves_title_fix():
    changelog = (ROOT / "docs/CHANGELOG.md").read_text(encoding="utf-8")

    from config.app_version import RELEASE_DATE
    assert changelog.startswith(f"## {RELEASE_DATE} - v{RELEASE_VERSION}")
    assert "Electron 런타임 버전 `43.4.0`" in changelog
    assert "사용자 화면에서 구현명 `Web UI`를 제거" in changelog


def test_every_manual_tab_has_a_rich_summary_and_readable_full_document():
    manual = json.loads((ROOT / "docs/USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    workspace = (ROOT / "webui/src/components/AssistantWorkspace.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui/src/styles.css").read_text(encoding="utf-8")

    assert manual["release_version"] == RELEASE_VERSION
    assert len(manual["sections"]) == 11
    assert manual["sections"][0]["id"] == "intro"
    for section in manual["sections"][1:]:
        assert f"  {section['id']}: {{" in workspace
    assert "parseManualDocument" in workspace
    assert "manual-document-body" in workspace
    assert "검색 결과 다음" in workspace
    assert "상세 원문 전체 보기" not in workspace
    assert "manual-guide-visual" in styles
    assert "manual-guide-notice" in styles
    assert "manual-doc-paragraph" in styles
    assert "manual-document-table" in styles


def test_manual_snapshot_preserves_canonical_content_and_has_no_encoding_loss():
    manual = json.loads((ROOT / "docs/USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    generated = build_snapshot()

    assert manual == generated
    assert [section["id"] for section in manual["sections"]] == [
        "intro", "live", "settings", "intelligence", "runtime", "assets",
        "stocks", "assistant", "custom", "arena", "updates",
    ]
    assert len({section["label"] for section in manual["sections"]}) == 11
    assert sum(len(section["content"]) for section in manual["sections"]) >= 180_000
    for section in manual["sections"]:
        assert len(section["content"]) >= 2_000
        assert "\ufffd" not in section["content"]
        assert "濡쒓렇" not in section["content"]


def test_manual_current_support_and_release_boundaries_match_runtime_registry():
    manual = json.loads((ROOT / "docs/USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    contents = {section["id"]: section["content"] for section in manual["sections"]}
    registry = public_venue_registry()
    crypto = [item for item in registry["venues"] if item["service"] == "blockchain"]
    stocks = [item for item in registry["venues"] if item["service"] == "stock"]

    assert len(crypto) == 7
    assert len(stocks) == 4
    for venue in crypto:
        assert venue["display_name"] in contents["assets"]
    for venue in stocks:
        assert venue["display_name"] in contents["stocks"]

    assert "Coinone: 시세·PAPER·통계·Strategy Studio 준비. 실제 계정 E2E 전 LIVE 차단" in contents["live"]
    assert "암호화폐 LIVE 준비 경로: Binance, Bybit, OKX, Bitget, Upbit, Bithumb" in contents["live"]
    assert "암호화폐 LIVE 준비 경로: Binance, Bybit, OKX, Bitget, Upbit, Bithumb, Coinone" not in contents["live"]
    assert "유안타·LS증권·대신·NH투자증권은 확장 검토 대상" in contents["stocks"]
    from config.app_version import PUBLIC_RELEASE_VERSION
    assert (
        f"v{RELEASE_VERSION} Windows stable/latest 배포 후보 · "
        f"공개 stable/latest는 v{PUBLIC_RELEASE_VERSION}"
    ) in contents["custom"]
    assert 0 <= contents["updates"].find(f"v{RELEASE_VERSION} 최신 업데이트") < contents["updates"].find("v3.9.1.30 업데이트")

    for section_id in ("live", "settings", "assets", "stocks", "custom", "updates"):
        assert f"v{RELEASE_VERSION}" in contents[section_id]
    assert "v3.9.1.28 처음 사용 · 빠른 시작" not in contents["settings"]


def test_manual_current_strategy_and_alpha_arena_terms_match_runtime_contracts():
    manual = json.loads((ROOT / "docs/USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    contents = {section["id"]: section["content"] for section in manual["sections"]}

    assert "현재 7개 코인 거래소와 4개 증권사" in contents["custom"]
    assert "자산군·상품 유형·기관·시장국면·증거 단계" in contents["custom"]
    assert "통합 5개 거래소" not in contents["custom"]
    assert "6개 거래소와 4개 증권사" not in contents["custom"]
    assert "과거 시세 재생 검사" in contents["custom"]
    assert f"v{RELEASE_VERSION}에서는 Windows·주문 소유권·복구 E2E가 끝나기 전까지 LIVE를 실패 폐쇄" in contents["arena"]
    assert "현재는 PAPER 결과만 기록" in contents["arena"]
    assert "자동 주문 시도(사용자가 Arena를 켠 경우)" not in contents["arena"]
