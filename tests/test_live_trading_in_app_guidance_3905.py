from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_fix_patch_build_is_identifiable_inside_client():
    from config.app_version import (
        DASHBOARD_TITLE,
        RELEASE_BUILD_LABEL,
        RELEASE_NOTICE_ID,
        USER_MANUAL_TITLE,
    )

    assert RELEASE_BUILD_LABEL == "v3.9.0.10 AI Custom Management & Runtime Integrity Update"
    assert "AI Custom Management & Runtime Integrity Update" in DASHBOARD_TITLE
    assert "AI Custom Management & Runtime Integrity Update" in USER_MANUAL_TITLE
    assert "ai-custom-management-settings-tab-runtime-integrity-source-candidate" in RELEASE_NOTICE_ID


def test_user_guide_covers_all_live_venues_modes_and_memberships():
    from ui.live_trading_guidance import build_live_trading_guide

    guide = build_live_trading_guide("v3.9.0.8 AI Custom Update")
    for name in (
        "Binance",
        "Bybit",
        "OKX",
        "Bitget",
        "Upbit",
        "Bithumb",
        "키움증권",
        "신한증권",
        "미래에셋증권",
        "한국투자증권 KIS",
    ):
        assert name in guide
    for term in (
        "PAPER > LIVE > LEARNING",
        "전역 실주문 허용",
        "해당 증권사 LIVE 허용",
        "parallel",
        "레퍼럴",
        "프로 코인",
        "프로 증권",
        "프리미엄",
        "출금 권한",
    ):
        assert term in guide


def test_manual_has_dedicated_live_readiness_tab_and_quick_link():
    manual = _read("ui/widgets/user_manual_widget.py")

    assert '("실거래 준비", "실거래 준비")' in manual
    assert "self.create_live_trading_guide_tab(tab_widget)" in manual
    assert 'tab_widget.add("실거래 준비")' in manual
    assert "build_live_trading_guide(RELEASE_BUILD_LABEL)" in manual
    assert "새 Windows EXE의 크기·SHA-256·설치 검증 전" in manual
    assert "manifest는 pending_windows_rebuild" in manual


def test_dashboard_shows_once_and_keeps_permanent_live_readiness_entry():
    dashboard = _read("ui/dashboard_modern.py")

    assert "def _show_live_readiness_notice_if_needed" in dashboard
    assert 'settings_obj.get("acknowledged_client_notices", [])' in dashboard
    assert "RELEASE_NOTICE_ID not in notices" in dashboard
    assert 'text="실거래 필수 · 업데이트·사용법"' in dashboard
    assert 'self._open_manual_modal("실거래 준비")' in dashboard
    assert "build_live_trading_summary(RELEASE_BUILD_LABEL)" in dashboard


def test_settings_keeps_live_requirements_visible_before_user_enables_orders():
    settings = _read("ui/settings_modern.py")

    assert "def _show_live_trading_readiness_dialog" in settings
    assert 'text="실거래 필수 안내"' in settings
    assert "LIVE는 별도 권한입니다" in settings
    assert "PAPER OFF + 주문 대상/증권 LIVE + API 준비 + 가드레일" in settings
    assert "build_live_trading_guide(RELEASE_BUILD_LABEL)" in settings
