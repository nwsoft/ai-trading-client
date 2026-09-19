from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from trading.alpha_arena.runner import AlphaArenaRunner
from web_platform.advanced_services import AdvancedFeatureServices
from web_platform.application_services import ApplicationServices, DetachedRuntimeBridge
from web_platform.gateway import create_gateway_app
from web_platform.query_services import AccountQueryService
from web_platform.runtime_bridge import HeadlessRuntimeBridge


ROOT = Path(__file__).resolve().parents[1]
TOKEN = "advanced-feature-test-token-at-least-32-characters"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
CONFIRMED = {**AUTH, "X-NoahAI-Intent": "confirmed"}


def _advanced(tmp_path: Path) -> AdvancedFeatureServices:
    return AdvancedFeatureServices(
        data_dir=tmp_path,
        queries=AccountQueryService(db_path=str(tmp_path / "missing-account.db")),
    )


def test_portfolio_analysis_separates_currencies_and_never_auto_applies(tmp_path):
    service = _advanced(tmp_path)
    snapshot = service.portfolio_analysis(account_snapshot={
        "sources": {
            "binance": {"positions": [{"symbol": "BTCUSDT", "quantity": 0.1, "mark_price": 50000}]},
            "upbit": {"positions": [{"symbol": "BTCKRW", "quantity": 0.01, "price": 100000000}]},
        }
    })

    assert set(snapshot["allocation_by_currency"]) == {"USDT", "KRW"}
    assert snapshot["allocation_by_currency"]["USDT"]["total_value"] == 5000
    assert snapshot["allocation_by_currency"]["KRW"]["total_value"] == 1_000_000
    assert snapshot["currency_separation"] is True
    assert snapshot["recommendations_only"] is True
    assert snapshot["correlation"]["status"] == "insufficient_data"


def test_life_finance_advanced_engines_return_real_empty_state_and_reference_results(tmp_path):
    service = _advanced(tmp_path)
    from trading.life_finance import LifeFinanceManager

    manager = LifeFinanceManager(data_dir=str(tmp_path / "life"))
    analysis = service.life_finance_analysis(manager)
    assert analysis["projection_basis"]["monthly_income"] == 0
    assert analysis["projection"] == [0.0] * 12

    catalog = service.product_catalog()
    assert catalog["counts"]["loan"] > 0
    assert "path" not in json.dumps(catalog)
    compared = service.compare_product(product_type="savings", amount=10_000_000, term_months=12, category=None)
    assert compared["application_submitted"] is False
    assert compared["result"]["best"]["expected_interest"] >= 0

    tax = service.calculate_tax(calculation="financial_income", values={
        "interest_income": 15_000_000,
        "dividend_income": 6_000_000,
        "annual_salary": 50_000_000,
    })
    assert tax["result"]["subject_to_comprehensive_tax"] is True
    assert tax["official_filing"] is False


def test_financial_intelligence_snapshot_is_read_only_and_market_refresh_is_explicit(tmp_path):
    service = _advanced(tmp_path)
    snapshot = service.financial_intelligence_snapshot(service="blockchain")
    assert snapshot["direct_trade_signal"] is False
    assert snapshot["summary"]["data_status"] == "insufficient_data"
    refreshed = service.refresh_financial_market(
        service="blockchain",
        universe=[{
            "symbol": "BTCUSDT",
            "asset_type": "crypto",
            "points": [
                {"timestamp": "2026-08-13T00:00:00+00:00", "open": 100, "high": 110, "low": 90, "close": 105, "volume": 2},
                {"timestamp": "2026-08-14T00:00:00+00:00", "open": 105, "high": 115, "low": 100, "close": 110, "volume": 3},
            ],
        }],
        use_network=False,
    )
    assert refreshed["direct_trade_signal"] is False
    assert refreshed["market"]["summaries"][0]["symbol"] == "BTCUSDT"
    assert refreshed["market"]["_chart_points"][-1]["close"] == 110


def test_advanced_gateway_requires_auth_and_explicit_intent(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))

    assert client.get("/api/v1/portfolio/analysis").status_code == 401
    portfolio = client.get("/api/v1/portfolio/analysis", headers=AUTH)
    assert portfolio.status_code == 200
    assert portfolio.json()["currency_separation"] is True
    assert client.post("/api/v1/portfolio/snapshot", headers=AUTH, json={}).status_code == 428

    body = {"product_type": "savings", "amount": 10_000_000, "term_months": 12, "category": None}
    assert client.post("/api/v1/life-finance/products/compare", headers=AUTH, json=body).status_code == 428
    compared = client.post("/api/v1/life-finance/products/compare", headers=CONFIRMED, json=body)
    assert compared.status_code == 200
    assert compared.json()["application_submitted"] is False

    preferred = client.post(
        "/api/v1/life-finance/products/compare",
        headers=CONFIRMED,
        json={**body, "credit_score": "좋음 (750~900)"},
    )
    assert preferred.status_code == 200
    assert preferred.json()["credit_profile"] == "좋음 (750~900)"
    assert "신용도" in preferred.json()["result"]["summary"]

    unknown = dict(body, unexpected=True)
    assert client.post("/api/v1/life-finance/products/compare", headers=CONFIRMED, json=unknown).status_code == 422


def test_financial_intelligence_action_requires_intent_and_stays_read_only(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))
    body = {"service": "ai_analyst", "action": "macro", "payload": {}}

    assert client.post("/api/v1/financial-intelligence/action", headers=AUTH, json=body).status_code == 428
    response = client.post("/api/v1/financial-intelligence/action", headers=CONFIRMED, json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["service"] == "ai_analyst"
    assert result["action"] == "macro"
    assert result["direct_trade_signal"] is False
    assert result["order_submitted"] is False

    unsupported = {"service": "stock", "action": "events", "payload": {}}
    assert client.post(
        "/api/v1/financial-intelligence/action", headers=CONFIRMED, json=unsupported
    ).status_code == 400


def test_portfolio_snapshot_save_uses_server_analysis_and_preserves_currency_separation(tmp_path, monkeypatch):
    import web_platform.application_services as service_module

    stored = {"stock_asset_mode": "all", "unknown_user_key": {"keep": True}}
    monkeypatch.setattr(service_module, "get_app_data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(service_module, "set_current_user_account", lambda account: None)
    monkeypatch.setattr(service_module, "load_settings", lambda **kwargs: dict(stored))

    def fake_save(payload):
        stored.clear()
        stored.update(payload)
        return True

    monkeypatch.setattr(service_module, "save_settings", fake_save)
    monkeypatch.setattr(
        service_module,
        "patch_settings_paths",
        lambda changes: stored.update(changes) is None,
    )
    services = ApplicationServices(account="tester", runtime_bridge=DetachedRuntimeBridge())
    services._latest_account_snapshot = {
        "sources": {
            "binance": {"positions": [{"symbol": "BTCUSDT", "quantity": 0.1, "mark_price": 50000}]},
            "upbit": {"positions": [{"symbol": "BTCKRW", "quantity": 0.01, "price": 100000000}]},
        }
    }
    client = TestClient(create_gateway_app(token=TOKEN, application_services=services))

    response = client.post("/api/v1/portfolio/snapshot", headers=CONFIRMED, json={})
    assert response.status_code == 200
    snapshot = response.json()["saved_snapshot"]
    assert snapshot["currency_totals"] == {"USDT": 5000.0, "KRW": 1_000_000.0}
    assert snapshot["display_currency"] is None
    assert snapshot["total_assets"] == 0.0
    assert stored["unknown_user_key"] == {"keep": True}
    assert stored["asset_insight_snapshot"]["saved_at"]


def test_alpha_arena_paper_decisions_never_call_exchange_order():
    class Client:
        def get_position_info(self, symbol): return {"positionAmt": 0}

    runner = AlphaArenaRunner(
        binance_client=Client(),
        settings={"paper_trading": True, "alpha_arena": {"max_risk_per_tick": 100}},
    )
    calls = []
    runner.running = True
    runner.order_executor.execute_trading_decision = lambda *args, **kwargs: calls.append((args, kwargs)) or {"status": "SUCCESS"}
    runner.order_executor._check_trade_gates = lambda *args, **kwargs: {"allowed": True}
    runner.on_order_result = lambda symbol, result: calls.append((symbol, result))
    runner._execute_trading_decisions({"BTC": {
        "signal": "ENTER_LONG", "profit_target": 110, "stop_loss": 90, "risk_usd": 10,
    }})

    assert len(calls) == 1
    assert calls[0][1]["status"] == "SIMULATED"
    assert calls[0][1]["order_submitted"] is False


def test_headless_bridge_alpha_arena_is_lazy_and_live_fail_closed(monkeypatch):
    settings = {"paper_trading": False, "alpha_arena": {"enabled": True, "symbols": ["BTCUSDT"]}}
    monkeypatch.setattr("web_platform.runtime_bridge.load_settings", lambda **kwargs: settings)
    calls = []

    class App:
        def alpha_arena_control(self, **kwargs):
            raise RuntimeError("alpha_arena_live_blocked_pending_external_gate")

    bridge = HeadlessRuntimeBridge(account="tester", factory=lambda account: calls.append(account) or App())
    assert bridge.alpha_arena_snapshot()["execution_mode"] == "LIVE_BLOCKED_PENDING_EXTERNAL_GATE"
    assert calls == []
    try:
        bridge.alpha_arena_control(action="start", live_confirmation=True)
    except RuntimeError as exc:
        assert str(exc) == "alpha_arena_live_blocked_pending_external_gate"
    else:
        raise AssertionError("LIVE AlphaArena must fail closed before the external gate")


def test_all_current_advanced_features_have_dedicated_react_routes():
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")
    api = (ROOT / "webui" / "src" / "api.ts").read_text(encoding="utf-8")
    for feature_id in (
        "blockchain.financial_intelligence", "blockchain.alpha_arena", "stock.financial_intelligence",
        "portfolio.insights", "portfolio.allocation", "portfolio.risk", "portfolio.performance",
        "personal_finance.service", "personal_finance.cashflow", "personal_finance.goals",
        "personal_finance.security", "personal_finance.tax",
        "ai_analyst.summary", "ai_analyst.intelligence",
    ):
        assert feature_id in surfaces
    assert 'const activeSurface = featureSurface(feature?.id)' in app
    assert 'activeSurface === "unmapped"' in app
    for endpoint in (
        "/api/v1/financial-intelligence", "/api/v1/portfolio/analysis", "/api/v1/alpha-arena",
        "/api/v1/life-finance/analysis", "/api/v1/life-finance/products", "/api/v1/life-finance/tax",
    ):
        assert endpoint in api

    inventory = json.loads((ROOT / "config" / "web_ui_feature_inventory.json").read_text(encoding="utf-8"))
    advanced_ids = {
        "blockchain.financial_intelligence", "blockchain.alpha_arena", "stock.financial_intelligence",
        "portfolio.insights", "portfolio.allocation", "portfolio.risk", "portfolio.performance",
        "personal_finance.service", "personal_finance.cashflow", "personal_finance.goals",
        "personal_finance.security", "personal_finance.tax",
        "ai_analyst.summary", "ai_analyst.intelligence",
    }
    states = {
        feature["id"]: feature["migration"]
        for service in inventory["services"] for feature in service["features"]
        if feature["id"] in advanced_ids
    }
    assert set(states) == advanced_ids
    assert "read_first" not in states.values()
    assert states["blockchain.alpha_arena"] == "source_connected_external_e2e_open"


def test_portfolio_web_ui_uses_legacy_user_facing_sections_without_raw_json():
    source = (ROOT / "webui" / "src" / "components" / "PortfolioWorkspace.tsx").read_text(encoding="utf-8")
    for label in (
        "통합 자산 현황", "자산군별 비중", "포트폴리오 집중도 (HHI)",
        "자산군 상관계수 히트맵", "리밸런싱 제안", "시나리오별 손실액 추정",
        "리스크 경고 및 대응 방향", "성과·위험 분석",
    ):
        assert label in source
    assert "JSON.stringify(data.risk_records" not in source
    assert "recommendations_only:" not in source
    assert "판단 보조 전용" in source
    assert "사용자의 승인 없이 주문 설정을 바꾸거나 거래를 실행하지 않습니다" in source


def test_financial_intelligence_web_ui_hides_internal_fields_and_raw_json():
    source = (ROOT / "webui" / "src" / "components" / "FinancialIntelligenceWorkspace.tsx").read_text(encoding="utf-8")
    assert "function readableLines" not in source
    assert '<pre className="legacy-intelligence-output"' not in source
    assert "HumanResult" in source
    for label in ("근거 기반 요약", "AI 판단", "AI 분석", "위험 근거", "실행 결과"):
        assert label in source
    for hidden in ("schema_version", "model_version", "rule_version", "chart_points"):
        assert hidden in source
    for preset in ("주요 시장", "국내 시장", "미국 시장", "가상자산", "직접 입력"):
        assert preset in source
    assert 'aria-label={t("시장 프리셋")}' in source
    assert 'aria-label={t("자산 유형")}' in source
    assert "universe" in source
    assert "disabled><option>{service ===" not in source
    for renderer in ("MarketResult", "ScreenerResult", "TechnicalResult", "BacktestResult"):
        assert f"function {renderer}" in source
    assert "INTELLIGENCE_CACHE" in source
    assert "setResult(null)" not in source
    assert "준비 중" in source
    assert "다른 탭으로 이동해도 이번 실행 중에는 조회 결과가 유지됩니다" in source


def test_stock_statistics_filters_server_rows_to_runtime_enabled_brokers():
    source = (ROOT / "webui" / "src" / "components" / "TradingStatisticsWorkspace.tsx").read_text(encoding="utf-8")
    assert 'service: "blockchain" | "stock"' in source
    assert 'service === "stock" ? "증권사 필터" : "거래소 필터"' in source
    assert 'service === "blockchain" && statisticsMode === "live"' in source
    assert "stockStatistics" not in source
    assert "stock_trade_stats" not in source


def test_ai_summary_and_scenario_have_readable_four_card_and_policy_layouts():
    intelligence = (ROOT / "webui" / "src" / "components" / "FinancialIntelligenceWorkspace.tsx").read_text(encoding="utf-8")
    scenario = (ROOT / "webui" / "src" / "components" / "AIAnalystScenarioWorkspace.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")
    assert "human-summary-metrics" in intelligence
    assert ".human-summary-metrics { grid-template-columns: repeat(4" in styles
    assert "주문 없는 사전 점검" in scenario
    assert "설정에서 불러온 값" in scenario
    assert "실제 주문을 만들지 않는 과거 시세 계산" in intelligence


def test_ai_analyst_preserves_legacy_preview_refresh_contract():
    source = (ROOT / "webui" / "src" / "components" / "AIAnalystWorkspace.tsx").read_text(encoding="utf-8")
    assert "AI 요약 리포트 미리보기" in source
    assert "시나리오 점검 미리보기" in source
    assert "미리보기 새로고침" in source
    assert "onOpenAssistant(prompt)" in source
    assert 'client.askAssistant(prompt, "ai_analyst"' not in source


def test_active_source_audit_detects_synology_web_conflict_files(tmp_path, monkeypatch):
    import scripts.active_source_audit as audit

    source = tmp_path / "webui" / "src" / "components"
    source.mkdir(parents=True)
    (source / "Workspace.tsx").write_text("export const ok = true;", encoding="utf-8")
    conflict = source / "Workspace_host_Aug-14-201347-2026_Conflict.tsx"
    conflict.write_text("export const broken = true;", encoding="utf-8")
    ignored = tmp_path / "webui" / "node_modules"
    ignored.mkdir(parents=True)
    (ignored / "Dependency_Conflict.tsx").write_text("", encoding="utf-8")

    monkeypatch.setattr(audit, "ROOT", tmp_path)

    assert audit._forbidden_active_sources() == [
        "webui/src/components/Workspace_host_Aug-14-201347-2026_Conflict.tsx"
    ]
