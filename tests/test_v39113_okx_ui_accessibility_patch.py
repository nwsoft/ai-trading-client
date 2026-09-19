from __future__ import annotations

import json
from pathlib import Path

from trading.notifications import SUPPORTED_EVENTS


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_ccxt_adapters_bound_network_calls_below_shutdown_deadline():
    for relative_path in (
        "trading/exchanges/adapters/okx_futures_adapter.py",
        "trading/exchanges/adapters/bybit_futures_adapter.py",
        "trading/exchanges/adapters/bitget_futures_adapter.py",
        "trading/exchanges/adapters/upbit_spot_adapter.py",
        "trading/exchanges/adapters/bithumb_spot_adapter.py",
    ):
        source = _text(relative_path)
        assert "'timeout': 12000" in source, relative_path

    unified = _text("trading/unified_trader.py")
    signal_call = unified.index("signal_data = self.analyzer.generate_trading_signal(")
    post_call_stop = unified.index("if not self.trading_cycles.get(exchange_name, False):", signal_call)
    result_store = unified.index("analysis_results[symbol]", signal_call)
    assert signal_call < post_call_stop < result_store


def test_exchange_status_and_paper_history_are_contained_and_collapsible():
    component = _text("webui/src/components/LegacyFeatureWorkspaces.tsx")
    actions = component.index('className="exchange-control-actions"')
    status = component.index("className={connectionClass}", actions)
    actions_end = component.index("</div>", status)
    assert actions < status < actions_end
    assert "aria-expanded={paperHistoryOpen}" in component
    assert 'paperHistoryOpen ? t("접기") : t("펼치기")' in component
    assert "setPaperHistoryOpen(false)" in component


def test_display_presets_are_persisted_and_applied_by_electron():
    settings = json.loads(_text("config/settings_template.json"))
    assert settings["ui_settings"]["display_preset"] == "display_standard"

    service = _text("web_platform/application_services.py")
    for option in ("display_standard", "display_large", "display_extra_large"):
        assert option in service

    main = _text("webui/electron/main.cjs")
    assert "mainWindow.webContents.setZoomFactor(profile.zoom)" in main
    assert "screen.getDisplayMatching(mainWindow.getBounds()).workAreaSize" in main
    assert 'ipcMain.handle("window:apply-display-preferences"' in main


def test_update_available_is_an_opt_in_channel_event_with_gateway_route():
    settings = json.loads(_text("config/settings_template.json"))
    assert settings["notification_integrations"]["events"]["update_available"] is True
    assert "update_available" in SUPPORTED_EVENTS
    assert "/api/v1/notifications/update-available" in _text("web_platform/gateway.py")
    update_center = _text("webui/src/components/UpdateCenter.tsx")
    assert "notifyUpdateAvailable" in update_center
    assert "noahai:update-notified:${encodeURIComponent(accountScope)}:${target}" in update_center
    assert "!accountScope" in update_center
    assert "[client, currentVersion, accountScope]" in update_center
    assert 'result.queued === true' in update_center


def test_strategy_studio_explains_explicit_parallel_live_paper_validation():
    component = _text("webui/src/components/StrategyStudio.tsx")
    assert "현재 LIVE · 독립 PAPER 병행검증 가능" in component
    assert "현재 LIVE · 독립 PAPER 병행검증 꺼짐" in component
    assert "거래소 주문 API를 소유하지 않으며 검증 통과도 자동 LIVE 적용되지 않습니다." in component
