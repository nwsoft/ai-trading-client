import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _legacy_service_tab_order(service: str) -> list[str]:
    spec = importlib.util.spec_from_file_location("service_tab_policy", ROOT / "ui" / "service_tab_policy.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.get_service_tab_order(service))


def test_web_service_information_architecture_exactly_matches_legacy_policy() -> None:
    payload = json.loads((ROOT / "config" / "web_ui_feature_inventory.json").read_text(encoding="utf-8"))
    services = {service["id"]: service for service in payload["services"]}

    assert [service["label"] for service in payload["services"]] == [
        "블록체인", "주식/증권", "자산 통합", "생활금융", "AI애널리스트",
    ]
    mapping = {
        "blockchain": "blockchain",
        "stock": "stock",
        "portfolio": "real_estate",
        "personal_finance": "other",
        "ai_analyst": "ai_analyst",
    }
    for web_service, legacy_service in mapping.items():
        labels = [
            feature["label"]
            for feature in services[web_service]["features"]
            if not feature["id"].endswith("source_workspaces")
        ]
        assert labels == _legacy_service_tab_order(legacy_service), (web_service, labels)


def test_shared_product_contract_covers_all_services_settings_and_manual() -> None:
    from config.product_ui_contract import (
        AI_ANALYST_CARDS,
        LIFE_FINANCE_INNER_TABS,
        LIFE_FINANCE_QUICK_ACTIONS,
        MANUAL_SECTION_LABELS,
        PORTFOLIO_INSIGHT_SECTIONS,
        SERVICE_FEATURE_LABELS,
        SERVICE_ORDER,
        SETTINGS_SECTION_LABELS,
    )
    from web_platform.feature_inventory import load_feature_inventory

    payload = load_feature_inventory()
    assert tuple((item["id"], item["label"]) for item in payload["services"]) == SERVICE_ORDER
    assert {
        item["id"]: tuple(feature["label"] for feature in item["features"])
        for item in payload["services"]
    } == SERVICE_FEATURE_LABELS
    assert tuple(payload["ui_contract"]["settings_sections"]) == SETTINGS_SECTION_LABELS
    assert tuple(payload["ui_contract"]["manual_sections"]) == MANUAL_SECTION_LABELS
    assert tuple(payload["ui_contract"]["life_finance_inner_tabs"]) == LIFE_FINANCE_INNER_TABS
    assert tuple(payload["ui_contract"]["life_finance_quick_actions"]) == LIFE_FINANCE_QUICK_ACTIONS
    assert tuple(payload["ui_contract"]["portfolio_insight_sections"]) == PORTFOLIO_INSIGHT_SECTIONS
    assert tuple(payload["ui_contract"]["ai_analyst_cards"]) == AI_ANALYST_CARDS


def test_settings_ai_help_keeps_settings_context_in_assistant() -> None:
    app_source = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assistant_source = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")

    assert 'onAskAssistant={(question, settingsSection) => openAssistant(question, "settings", settingsSection)}' in app_source
    assert 'settingsSection={context.service === "settings" ? context.section : ""}' in app_source
    assert '설정 문맥 고정' in assistant_source
    assert 'settings: {' in assistant_source
    assert 'title: "설정·연결 자주 묻는 질문"' in assistant_source


def test_stock_ai_learning_and_reports_use_runtime_enabled_sources() -> None:
    app_source = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    workspace_source = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")

    assert app_source.count("sources={activeSourceTabs}") >= 2
    assert 'sourceOptions = sources.filter((item) => allowedSources.includes(item))' in workspace_source
    assert '설정에서 사용할 증권사를 선택하세요.' in workspace_source


def test_exported_manual_has_no_unresolved_user_visible_placeholders() -> None:
    from ui.ai_custom_guidance import build_ai_custom_provider_guide, build_ai_custom_safe_flow

    payload = json.loads((ROOT / "docs" / "USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    sections = {section["id"]: section["content"] for section in payload["sections"]}
    assert not any(re.search(r"\{\{[A-Z0-9_]+\}\}", content) for content in sections.values())
    assert build_ai_custom_safe_flow().splitlines()[0] in sections["intro"]
    assert build_ai_custom_provider_guide().splitlines()[0] in sections["custom"]


def test_exported_assistant_manual_matches_current_web_read_only_contract() -> None:
    payload = json.loads((ROOT / "docs" / "USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    sections = {section["id"]: section["content"] for section in payload["sections"]}
    assistant = sections["assistant"]

    assert "「일반 안내」는 외부 Provider를 호출하지 않으므로" in assistant
    assert "OpenAI 등 생성형 AI API 키 없이 사용할 수 있습니다" in assistant
    assert "어시스턴트가 설정을 몰래 저장하거나 주문을 실행하지는 않습니다" in assistant
    assert "변경은 사용자가 위 설정 경로에서 직접 선택" in assistant
    assert "두 버튼 모두 현재값·제안값·근거·위험을 비교" in assistant
    assert "API 키를 넣고 저장합니다" not in assistant
    assert "JSON 등으로 반영하려 시도" not in assistant
    assert "변경 전/후 확인과 최종 확인 뒤 저장" not in assistant
    assert "말로 설정만 바꾸는 요청은 될 수 있습니다" not in assistant


def test_web_ai_execution_record_includes_financial_intelligence_events() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    for prefix in ["assistant.", "strategy.", "alpha_arena.", "financial_intelligence."]:
        assert f'"{prefix}"' in app


def test_gateway_errors_are_translated_before_reaching_the_user() -> None:
    api = (ROOT / "webui" / "src" / "api.ts").read_text(encoding="utf-8")
    assert "userFacingGatewayError(payload.detail, response.status)" in api
    assert "로그인 세션을 다시 확인하세요." in api
    assert "아이디 또는 패스워드를 확인하세요." in api
    assert "throw new Error(detail)" not in api


def test_life_finance_and_ai_analyst_keep_legacy_nested_function_contracts() -> None:
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")
    analyst = (ROOT / "webui" / "src" / "components" / "AIAnalystWorkspace.tsx").read_text(encoding="utf-8")
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")

    for label in ["대시보드", "거래", "목표", "분석", "차트", "금융상품", "AI 어시스턴트"]:
        assert label in operations
    for label in ["AI 통합 애널리스트", "포트폴리오 종합 분석", "시장 신호 & 매매 타이밍", "리스크 평가 & 경고", "AI 맞춤 투자 조언", "성과 분석 & 비교", "뉴스 & 감성 분석", "AI 분석 결과"]:
        assert label in analyst
    assert '"ai_analyst.assistant": "assistant"' in surfaces
    assert '"ai_analyst.workspace": "ai_analyst"' in surfaces
    assert 'activeSurface === "assistant"' in app
    assert 'activeSurface === "ai_analyst"' in app


def test_assistant_navigation_keeps_each_service_context_and_legacy_location() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")
    assistant = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    service = (ROOT / "web_platform" / "application_services.py").read_text(encoding="utf-8")

    assert 'blockchain: "blockchain.ai_assistant"' in app
    assert 'stock: "stock.ai_assistant"' in app
    assert 'ai_analyst: "ai_analyst.assistant"' in app
    assert 'service === "personal_finance"' in app
    assert 'setActiveFeature("personal_finance.service")' in app
    assert 'setLifeAssistantRequest((value) => value + 1)' in app
    assert 'service === "portfolio"' in app
    assert 'setActiveFeature("ai_analyst.assistant")' in app
    assert 'service={context.service}' in app
    assert 'setAssistantService(activeService)' in app
    assert 'setInnerTab("AI 어시스턴트")' in operations
    assert 'service="personal_finance"' in operations
    assert 'title: "자산 통합 AI 상담"' in assistant
    assert 'context["life_finance"] = sanitize_settings(self.life_finance_snapshot())' in service


def test_portfolio_insight_keeps_legacy_snapshot_action_and_section_order() -> None:
    source = (ROOT / "webui" / "src" / "components" / "PortfolioWorkspace.tsx").read_text(encoding="utf-8")
    service = (ROOT / "web_platform" / "application_services.py").read_text(encoding="utf-8")
    gateway = (ROOT / "web_platform" / "gateway.py").read_text(encoding="utf-8")
    positions = [source.index(label) for label in ["통합 자산 현황", "자산군별 비중", "리스크 요약", "추천 액션"]]
    assert positions == sorted(positions)
    assert "현재 상태 저장" in source
    assert "savePortfolioSnapshot" in source
    assert "def save_portfolio_snapshot" in service
    assert '"/api/v1/portfolio/snapshot"' in gateway


def test_ai_analyst_scenario_uses_a_dedicated_legacy_contract_workspace() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")
    scenario = (ROOT / "webui" / "src" / "components" / "AIAnalystScenarioWorkspace.tsx").read_text(encoding="utf-8")
    assert '"ai_analyst.scenario": "ai_analyst_scenario"' in surfaces
    assert 'activeSurface === "ai_analyst_scenario"' in app
    assert "AIAnalystScenarioWorkspace" in app
    for label in ["자동매매 시나리오 점검", "데이터 기준", "현재 자동매매 정책", "과거 손익 민감도 결과", "보수", "공격"]:
        assert label in scenario


def test_web_login_uses_legacy_client_structure() -> None:
    login = (ROOT / "webui" / "src" / "components" / "LoginScreen.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "legacy-login-window" in login
    assert "legacy-login-logo-image" in login
    assert 'src="/icon.png"' in login
    assert "NoahAI Decision OS" in login
    assert "AI 재테크 의사결정 파트너" in login
    assert "패스워드" in login
    assert "회원가입" in login
    assert "legacy-login-window" in styles
    assert "width: 450px" in styles
    assert "min-height: 680px" in styles


def test_web_dashboard_shell_uses_legacy_client_chrome() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "legacy-dashboard-shell" in app
    assert "legacy-topbar" in app
    assert "legacy-user-chip" in app
    assert "legacy-source-chip" in app
    assert "legacy-content-frame" in app
    assert "legacy-statusbar" in app
    assert "AI 실행 기록 없음" in app
    assert "NoahAI-AI 금융 동반자" in app
    assert "| MODE ${mode} | EXCHANGE ${exchange} | TIME ${time}" in app
    assert '.map((value) => String(value).padStart(2, "0"))' in app
    assert '.join(":")' in app
    assert "toLocaleTimeString" not in app
    assert "자동매매: 대상" not in app
    assert "자동매매: 정지" not in app
    assert 'activeService === "blockchain" ? CRYPTO_SOURCES : null' not in app
    assert "실거래 필수 · 업데이트·사용법" in (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")
    assert "selectSourceTab" in app
    assert "source-tab" in app
    assert 'className="feature-tab-strip"' in app
    assert 'className="source-tab-strip"' in app
    assert 'aria-label={activeService === "stock" ? "증권사 선택" : "거래소 선택"}' in app
    assert "CRYPTO_SOURCES" in app
    assert "STOCK_SOURCES" in app
    assert "activeSourceTabs.map" in app
    assert "runtime.enabled_sources_by_service?.[service]" in app
    assert 'activeService === "stock" ? STOCK_SOURCES : CRYPTO_SOURCES' not in app
    assert "설정에서 사용할" in app
    assert 'feature?.id.endsWith("source_workspaces") && chartSource === source' in app
    assert '"blockchain.coin_info": "asset_info"' in surfaces
    assert "AssetInfoWorkspace" in app
    assert "SourceWorkspace" in app

    assert "legacy-dashboard-shell" in styles
    assert "legacy-topbar" in styles
    assert "legacy-content-frame" in styles
    assert "service-blockchain.active" in styles
    assert "service-stock.active" in styles
    assert "service-portfolio.active" in styles
    assert "service-personal_finance.active" in styles
    assert "service-ai_analyst.active" in styles
    assert "button.source-tab" in styles
    assert ".feature-tab-strip" in styles
    assert ".source-tab-strip" in styles
    assert "@media (max-width: 1500px)" in styles
    assert "min-width: 120px" in styles
    assert "grid-template-columns: minmax(330px, 3fr) minmax(430px, 4fr) minmax(255px, 2fr)" in styles


def test_exchange_control_status_does_not_collapse_below_adjacent_cards() -> None:
    workspace = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert 'runtime-strategy-status ${appliedCustomStrategies.length ? "applied"' in workspace
    assert 'role="status"' in workspace
    assert "현재 적용·검증 전략이 없습니다. 기본 NoahAI PAPER 운용은 계속됩니다." in workspace
    assert "grid-template-rows: max-content max-content minmax(160px, 1fr) max-content max-content" in styles
    assert ".legacy-exchange-left" in styles and "overflow-y: auto" in styles
    assert ".runtime-strategy-status.empty" in styles


def test_electron_login_window_uses_legacy_size_and_dashboard_resize() -> None:
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "webui" / "electron" / "preload.cjs").read_text(encoding="utf-8")
    types = (ROOT / "webui" / "src" / "vite-env.d.ts").read_text(encoding="utf-8")

    assert "width: 450" in main
    assert "height: 680" in main
    assert "useContentSize: true" in main
    assert "setContentSize(450, 680" in main
    assert "NoahAI Finance Decision OS - 로그인" in main
    assert "applyWindowMode" in main
    assert "window:set-mode" in main
    assert "width: 1500" not in main.split("new BrowserWindow", 1)[1].split("});", 1)[0]
    assert "setSize(1500, 980" in main
    assert "setMode" in preload
    assert 'setMode: (mode: "login" | "dashboard")' in types


def test_login_help_restores_the_legacy_popup_contract() -> None:
    login = (ROOT / "webui" / "src" / "components" / "LoginScreen.tsx").read_text(encoding="utf-8")
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "webui" / "electron" / "preload.cjs").read_text(encoding="utf-8")

    assert "LoginHelpScreen" in login
    assert "로그인 안내" in login
    assert "이용·책임 참고" in login
    assert "공식 안내(웹)" in login
    assert "window:open-login-help" in main
    assert "openLoginHelp" in preload


def test_dashboard_defaults_to_legacy_log_workspace_and_real_audit_record() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")

    assert 'useState("blockchain.logs")' in app
    assert "LegacyTradingLogWorkspace" in app
    assert "client.auditExport()" in app
    assert "setAiRecord" in app
    assert '!item.id.endsWith("source_workspaces")' in app
    assert "LegacyTradingLogWorkspace" in operations
    assert "운영 KPI" in operations
    assert "legacy-kpi-card" in operations
    assert '<option>DEBUG</option>' not in operations
    assert "LogHelpDialog" in operations
    assert "clearMarkerRef" in operations
    assert "거래 시그널만" in operations
    assert "거래 시그널|거래 실행|포지션|분석 완료" in operations
    assert "XAI 판단·체결 감사" not in operations
    assert "XAI 기반 판단 기록" not in operations
    reports = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    assert "실행 품질" in reports
    assert "setSelectedSource" in reports
    assert 'value={selectedSource}' in reports
    assert 'disabled={!sourceOptions.length}' in reports
    assert 'onChange={(event) => setSelectedSource(event.target.value)}' in reports
    assert "setReportSource" in reports
    assert 'value={reportSource} onChange=' in reports
    assert '<select value="전체" disabled>' not in reports
    assert "60 * 60 * 1000" in reports
    assert "AI 어시스턴트에 전달" in reports
    assert "realtimeFees" in reports
    assert 'client.logs(service as "blockchain" | "stock", "all", 100)' in operations
    assert 'client.workspace(service, `${service}.logs`, "", { statisticsPeriod: "today", statisticsMode })' in operations
    assert 'client.workspace(service, `${service}.statistics`, runtime?.selected_source ?? "")' not in operations
    assert "<span>포지션</span><b>{runningCount}</b>" not in operations
    assert "API 키가 설정되지 않았습니다." in operations
    assert 'client.logs(service, source, 100)' in reports
    assert "runtimeForService" in app
    assert "enabled_sources_by_service" in app
    assert 'useState<Record<"blockchain" | "stock", string>>' in app
    assert 'activeService === "stock" ? selectedSources.stock : selectedSources.blockchain' in app
    assert "serviceRuntime?.selected_source ?? chartSource" not in app
    assert "운영 화면을 불러오는 중입니다." in app
    assert "session?.authenticated && loading && !features" in app
    assert app.count("source={chartSource}") >= 5
    assert "useRef<HTMLDivElement | null>" in operations
    assert "consoleElement.scrollTop = consoleElement.scrollHeight" in operations
    # Credential and adapter failures are part of the legacy realtime log.
    # The status card may fail closed, but the log console must not erase the
    # evidence merely because the current credential snapshot is false.
    assert "const operationalLines = visibleLines.filter" not in operations
    assert "Do not hide those rows based on the current settings snapshot" in operations

    source_workspace = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    assert "if (!credentialsConfigured)" in source_workspace
    assert "API 키를 설정한 뒤 연결을 확인하세요." in source_workspace
    assert "credentialsConfigured\n        ? client.logs(service, source, 100)" in source_workspace
    assert 'lines: []' in source_workspace
    assert "미연결 상태에서는 과거 로그를 현재 연결 기록처럼 표시하지 않습니다." in source_workspace
    assert "client.refreshAccounts([source], false)" in source_workspace
    assert "7_000" in source_workspace


def test_log_help_dialog_matches_legacy_dedicated_popup_contract() -> None:
    dialog = (ROOT / "webui" / "src" / "components" / "LogHelpDialog.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "실시간 로그 해석 가이드" in dialog
    assert "사용자 매뉴얼(업데이트) 열기" in dialog
    assert "[코인 로그 질문 예시]" in dialog
    assert "[증권 로그 질문 예시]" in dialog
    assert "width: min(760px" in styles
    assert "height: min(560px" in styles


def test_all_inventory_features_fail_closed_instead_of_using_a_generic_workspace() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert 'from "./components/DataWorkspace"' not in app
    assert "<DataWorkspace" not in app
    assert not (ROOT / "webui" / "src" / "components" / "DataWorkspace.tsx").exists()
    assert "1:1 화면 연결 오류" in app
    assert "공용 대체 화면을 표시하지 않고 배포를 차단합니다." in app


def test_every_inventory_feature_has_exactly_one_dedicated_surface() -> None:
    inventory = json.loads((ROOT / "config" / "web_ui_feature_inventory.json").read_text(encoding="utf-8"))
    expected = {
        feature["id"]
        for service in inventory["services"]
        for feature in service["features"]
    }
    source = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")
    mapped = re.findall(r'^\s+"([^"]+)":\s+"[^"]+",$', source, flags=re.MULTILINE)

    assert len(mapped) == len(set(mapped)), "하나의 기능 ID가 둘 이상의 화면에 중복 연결되었습니다."
    assert set(mapped) == expected


def test_every_product_service_feature_is_source_connected_but_parity_remains_open() -> None:
    inventory = json.loads((ROOT / "config" / "web_ui_feature_inventory.json").read_text(encoding="utf-8"))
    states = {
        feature["id"]: feature["migration"]
        for service in inventory["services"]
        for feature in service["features"]
    }

    assert states
    assert all(state.startswith("source_connected") for state in states.values())
    assert all(state.endswith("_open") for state in states.values())


def test_complete_parity_source_auditor_covers_all_five_services() -> None:
    spec = importlib.util.spec_from_file_location(
        "audit_web_ui_full_parity_contract",
        ROOT / "scripts" / "audit_web_ui_full_parity_contract.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    errors, summary = module.audit()

    assert errors == []
    assert summary == {
        "services": 5,
        "top_level_features": 35,
        "institution_sources": 11,
        "life_finance_inner_routes": 7,
        "settings_sections": 9,
        "manual_sections": 11,
        "ai_analyst_cards": 6,
    }


def test_assistant_deep_analysis_uses_only_canonical_service_workspaces() -> None:
    source = (ROOT / "web_platform" / "application_services.py").read_text(encoding="utf-8")

    assert '"blockchain": "blockchain.logs"' in source
    assert '"stock": "stock.logs"' in source
    assert '"portfolio": "portfolio.insights"' in source
    assert '"ai_analyst": "ai_analyst.workspace"' in source
    assert 'feature="ai_analyst.report"' not in source
    assert 'f"{service}.overview"' not in source


def test_electron_development_launcher_removes_node_runtime_override() -> None:
    package = (ROOT / "webui" / "package.json").read_text(encoding="utf-8")
    launcher = (ROOT / "webui" / "electron" / "run-electron.cjs").read_text(encoding="utf-8")

    assert "node electron/run-electron.cjs" in package
    assert "delete environment.ELECTRON_RUN_AS_NODE" in launcher


def test_coin_and_exchange_tabs_use_dedicated_legacy_workspaces() -> None:
    workspaces = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    connection_helper = (ROOT / "webui" / "src" / "accountConnection.ts").read_text(encoding="utf-8")
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")

    assert "balanceEnvelope?.balance" in workspaces
    assert ".wallet_balance" in workspaces
    assert ".available_balance" in workspaces
    assert "exchange / balance / account_info" not in workspaces

    for label in ["선택된 거래", "(AI 평가 결과)", "심볼 직접 분석", "AI종합점수", "변동성점수", "리스크점수"]:
        assert label in workspaces
    for label in ["제어", "잔고", "포지션", "거래 통계", "실시간 새로고침"]:
        assert label in workspaces
    for label in ["API 키 연결 필요", "API 키 설정됨 · 연결 확인 중", "설정에서 API 연결하기"]:
        assert label in workspaces
    for label in ["API 인증 완료", "API 인증 실패", "계정 조회 실패", "앱 문자 처리 오류"]:
        assert label in connection_helper
    assert "credentialsConfigured\n        ? client.logs(service, source, 100)" in workspaces
    assert "client.refreshAccounts([source], true)" in workspaces
    assert "client.refreshAccounts([source], false)" in workspaces
    assert "7_000" in workspaces
    assert "commandBusy || !enabled || !credentialsConfigured" in workspaces
    assert "accountBusy || !credentialsConfigured" in workspaces
    assert "sourceLogConsoleRef" in workspaces
    assert "consoleElement.scrollTop = consoleElement.scrollHeight" in workspaces
    assert '"blockchain.trends": "market_trend"' in surfaces
    assert '"blockchain.coin_info": "asset_info"' in surfaces
    assert '"stock.info": "asset_info"' in surfaces
    assert '"blockchain.source_workspaces": "source_workspace"' in surfaces
    assert '"stock.source_workspaces": "source_workspace"' in surfaces


def test_desktop_icon_and_fixed_log_scroller_are_part_of_the_shell_contract() -> None:
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    package = (ROOT / "webui" / "package.json").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "productIconPath" in main
    assert "app.dock.setIcon" in main
    assert main.index('app.setName("NoahAI")') < main.index("app.whenReady()")
    assert '"icon": "build/icon.ico"' in package
    assert "body.dashboard-surface #root { height: 100vh" in styles
    assert ".legacy-log-console" in styles
    assert "height: 100%;" in styles


def test_electron_hides_default_desktop_menu_outside_macos() -> None:
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")

    assert "ipcMain, Menu, net: electronNet" in main
    assert 'if (process.platform !== "darwin") Menu.setApplicationMenu(null);' in main


def test_saved_login_uses_electron_os_encryption_instead_of_renderer_storage() -> None:
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "webui" / "electron" / "preload.cjs").read_text(encoding="utf-8")
    login = (ROOT / "webui" / "src" / "components" / "LoginScreen.tsx").read_text(encoding="utf-8")

    assert "safeStorage.encryptString" in main
    assert "safeStorage.decryptString" in main
    assert 'mode: 0o600' in main
    assert 'ipcRenderer.invoke("credentials:save"' in preload
    assert "localStorage" not in login
    assert "credentials?.load" in login
    assert "credentials?.save" in login


def test_assistant_keeps_legacy_chat_quick_questions_and_tools() -> None:
    assistant = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    for label in ["자주 하는 질문", "전송", "음성입력", "설정관리", "차트분석", "전체 복사", "TXT 저장"]:
        assert label in assistant
    for label in ["High vol 설정", "전략 스튜디오 사용법", "게이트 원인 점검", "거래 부재 원인", "증권 연결 점검"]:
        assert label in assistant
    for label in ["설명 수준", "초보자", "일반", "고급", "일반 안내", "심층분석 (외부 AI·비용)", "외부 호출 없음"]:
        assert label in assistant
    for contract in ["SpeechRecognition", "webkitSpeechRecognition", "speechSynthesis", "assistant_voice", "듣기 중지"]:
        assert contract in assistant


def test_settings_and_manual_restore_legacy_navigation_and_ai_help() -> None:
    settings = (ROOT / "webui" / "src" / "components" / "SettingsCenter.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")
    manual = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")

    for label in ["일반", "거래소 선택", "거래소 API", "AI 엔진/API", "알림·리포트", "고급 매매 계층", "AlphaArena", "AI 시스템 상태", "업데이트"]:
        assert label in settings
    assert "AI에게 묻기" in settings
    assert "필수 연결 정보가 이 계정 설정에 저장되어 있습니다" in settings
    assert "필수 연결 정보가 현재 계정 설정에 없습니다" in settings
    assert "UpdateCenter" in settings
    assert "field.section === section.id" in settings
    assert 'field.presentation === "primary"' in settings
    assert "function settingSection" not in settings
    assert "고급 설정 보기" in settings
    assert 'credentialProvider === "alpha:deepseek"' in settings
    assert 'if (section.id === "alpha") setCredentialProvider("alpha:deepseek")' in settings
    assert 'name === "alpha:deepseek"' in settings
    assert 'field.kind === "multiselect"' in settings
    assert 'field.kind === "model_select"' in settings
    assert "MODEL_PROVIDER_PATHS" in settings
    assert "accountModelCatalogs" in settings
    assert "모델을 선택하세요" in settings
    assert "setting-multiselect" in styles
    for label in [
        "초보자 연결 3단계",
        "거래소·증권 설정 도우미",
        "초기 자금 기준",
        "현재 고정 가드레일과 기본값",
        "코인 자동 보정 권장값 불러오기",
    ]:
        assert label in settings
    assert "GitHub 확인 버전" in (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")
    for label in ["백업에서 복구", "설정 백업 복구", "복구 직전 현재 설정도 자동 백업", "저장하지 않은 설정 변경"]:
        assert label in settings
    for label in ["설정 창 닫기", "저장 후 닫기", "저장하지 않고 닫기", "계속 편집"]:
        assert label in settings
    for label in ["AI 설정 도우미", "AI 답변 받기", "안전 추천안 만들기", "변경 미리보기", "변경 대기에 반영"]:
        assert label in settings
    assert 'client.askAssistant(question, "settings"' in settings
    assert "setDraft((current) => ({ ...current, ...guideProposal }))" in settings
    assert "아직 저장되지 않았습니다" in settings
    assert ".settings-window-close" in styles
    assert ".settings-guide-panel" in styles
    assert "async function save(" in settings
    assert 'scope: "section" | "all"' in settings
    assert 'save("section")' in settings
    assert 'save("all", current, false)' in settings
    assert "credentialDrafts" in settings
    assert "pendingCredentialProviders" in settings
    assert "saveAllPending(false)" in settings
    assert "saveAllPending(true)" in settings
    assert "파일 저장은 완료됐지만 화면 상태 새로고침에 실패했습니다" in settings
    assert "sectionChangedCount" in settings
    assert "scope === \"section\" && !savedPaths.has(field.path)" in settings
    assert "client.settingsBackups()" in settings
    assert "client.restoreSettings(" in settings
    for contract in ["client.settingsDiagnostics()", "client.checkAIProvider(", "client.refreshAccounts(", "저장된 키로 실제 연결 점검", "AI 모델·기능 실제 점검", "AI로 초기 설정 (5문항)", "지원 요약 복사", "지원 요약 파일 저장"]:
        assert contract in settings
    for label in [
        "바이낸스 (Binance) · 선물",
        "업비트 (Upbit) · 현물",
        "키움증권 (Kiwoom) · 주식/ETF",
        "한국투자증권 (KIS) · 주식/ETF",
        "기존 TP/SL 보호 유지",
        "NoahAI 소유 포지션만 청산",
    ]:
        assert label in settings
    assert "기능·설정·오류 검색" in manual
    assert "AI에게 묻기" in manual
    assert "client.manual()" in manual
    assert "snapshot.sections" in manual
    for contract in ["highlightedManualText", "<mark", "설정 화면 열기", "전략 스튜디오 화면 열기", "거래소 화면 열기", "증권사 화면 열기"]:
        assert contract in manual
    assert "const MANUAL_TABS" not in manual
    assert "docs/USER_MANUAL_SECTIONS.json" in (ROOT / "noahai_web_engine.spec").read_text(encoding="utf-8")
    assert "trading.notifications" in (ROOT / "noahai_web_engine.spec").read_text(encoding="utf-8")


def test_august_18_visual_parity_pass_keeps_status_reports_and_analyst_readable() -> None:
    workspaces = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")
    analyst = (ROOT / "webui" / "src" / "components" / "AIAnalystWorkspace.tsx").read_text(encoding="utf-8")
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")
    update = (ROOT / "webui" / "src" / "components" / "UpdateCenter.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert "accountUpdatedAt" not in workspaces
    for label in ["7초 자동 갱신", "근거 기반 요약", "거래 상태", "성과 계산", "체결 규모", "다음 확인"]:
        assert label in workspaces
    for contract in ["report-period-tabs", "report-summary-metrics", "account-refresh-status", "account-refresh-button"]:
        assert contract in workspaces
    for contract in [".legacy-ai-report > nav button", ".report-summary-metrics", ".account-refresh-status", ".account-refresh-button"]:
        assert contract in styles
    for label in ["PORTFOLIO", "MARKET SIGNAL", "RISK GUARD", "AI ADVICE", "PERFORMANCE", "NEWS & SENTIMENT"]:
        assert label in analyst
    for label in ["수입 변화", "지출 변화", "저축 변화", "지난달 대비 수입", "지난달 대비 지출", "지난달 대비 순저축"]:
        assert label in operations
    assert "currentVersion || installedVersion" in update


def test_alpha_arena_restores_first_visit_safety_guide() -> None:
    arena = (ROOT / "webui" / "src" / "components" / "AlphaArenaWorkspace.tsx").read_text(encoding="utf-8")
    for copy in ["Alpha Arena 모드 안내", "기본 가드레일", "60초 판단 주기(최소 30초)", "틱당 모델 제시 위험 합계 상한 1,500 USDT", "확인"]:
        assert copy in arena
    assert "showGuide" in arena


def test_life_finance_exposes_full_legacy_tax_inputs_and_human_results() -> None:
    life = (ROOT / "webui" / "src" / "components" / "LifeFinanceAdvanced.tsx").read_text(encoding="utf-8")
    operations = (ROOT / "webui" / "src" / "components" / "Operations.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")
    assistant = (ROOT / "webui" / "src" / "components" / "AssistantWorkspace.tsx").read_text(encoding="utf-8")
    for key in [
        "credit_card", "debit_cash", "medical_expense", "education_expense", "donation",
        "pension_savings", "irp_contribution", "personal_deduction_count", "interest_income",
        "dividend_income", "domestic_stock_profit", "overseas_stock_profit", "etf_profit",
        "other_profit", "annual_investment", "investment_years", "expected_return_rate", "isa_type",
    ]:
        assert key in life
    for label in ["세금 계산 결과", "절세 점검 제안", "생활금융 AI 상담", "대출 비교", "보험 점검", "신용 관리"]:
        assert label in life or label in assistant
    assert "legacy-product-table" in life
    assert '<pre className="json-summary"' not in life
    assert "life-finance-kpi-grid" in operations
    assert "life-finance-form" in operations
    assert ".finance-summary .life-finance-kpi-grid" in styles
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in styles


def test_ai_custom_source_input_keeps_legacy_rows_and_control_contract() -> None:
    strategy = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    for contract in [
        "legacy-strategy-controls", "legacy-signal-controls", "legacy-risk-controls",
        "소스에서 자동", "AI 분석 및 전략 초안 만들기", "국면 이탈 시",
    ]:
        assert contract in strategy
    assert "[10, 9, 8, 7, 6, 5, 4, 3, 2, 1]" in strategy
    assert ".legacy-strategy-controls { display: flex; align-items: center; flex-wrap: nowrap" in styles
    assert ".legacy-risk-controls { display: flex; align-items: center; flex-wrap: nowrap" in styles
    assert ".legacy-source-ingestor .legacy-risk-controls label { width: auto; flex: 0 0 auto; }" in styles


def test_web_manual_snapshot_is_exact_reachable_legacy_contract() -> None:
    source = ROOT / "ui" / "widgets" / "user_manual_widget.py"
    payload = json.loads((ROOT / "docs" / "USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))

    assert payload["source"] == "ui/widgets/user_manual_widget.py"
    assert payload["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert [section["label"] for section in payload["sections"]] == [
        "NoahAI 소개",
        "실거래 준비",
        "시작·설정",
        "금융 인텔리전스",
        "NoahAI 작동 원리",
        "자산별 사용 가이드",
        "증권/주식/ETF",
        "AI 어시스턴트",
        "전략 스튜디오",
        "AlphaArena",
        "업데이트",
    ]
    assert all(len(section["content"]) >= 1000 for section in payload["sections"])


def test_stock_ai_restores_independent_legacy_tabs_instead_of_an_invented_hub() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    inventory = (ROOT / "config" / "web_ui_feature_inventory.json").read_text(encoding="utf-8")
    surfaces = (ROOT / "webui" / "src" / "featureSurfaces.ts").read_text(encoding="utf-8")

    assert "StockAIHub" not in app
    assert not (ROOT / "webui" / "src" / "components" / "StockAIHub.tsx").exists()
    for feature_id in ["stock.ai_learning", "stock.ai_reports", "stock.ai_assistant", "stock.ai_custom"]:
        assert feature_id in inventory
        assert feature_id in surfaces
    for surface in ["ai_learning", "ai_report", "assistant", "strategy"]:
        assert f'activeSurface === "{surface}"' in app


def test_ai_custom_restores_legacy_source_xai_version_flow_and_contract_values() -> None:
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    for label in [
        "1. 전략 소스 입력",
        "저장 대상",
        "파일 선택",
        "AI 분석 및 전략 초안 만들기",
        "2. XAI 분석 결과와 적용값",
            "최종 재검증 후 전략 버전 저장",
        "3. 내 프라이빗 전략 버전",
        "전략 가져오기",
        "실행 풀",
    ]:
        assert label in studio
    for control in ["marketRegimes", "regimeScope", "priority", "signalMode", "riskPerTrade", "maxMargin", "leverageCap", "conflictFallback"]:
        assert control in studio
    assert "잘 모르겠어요 · NoahAI가 판단 (권장)" in studio
    assert "market_regimes: marketRegimes" in studio
    assert "suggestion.auto_select === true" in studio
    assert "normalizedSubmitSourceKind" in studio
    assert "source_kind: sourceKind ||" not in studio
    assert "strategy_key: versionTarget || undefined" in studio
    assert "이 결과 AI에게 묻기" in studio
    assert 'resultView === "Level 3 전체 근거"' in studio
    assert "고급 실행 규칙 편집" in studio
    assert "legacy-rule-override-confirm" in studio
    assert "직접 편집한 JSON을 사용자 선언 규칙으로 저장" in studio
    assert "체크해도 검증을 우회하지 않으며" in studio
    assert 'aria-describedby="legacy-rule-override-help"' in studio
    assert "strategy-draft-validation-help" in studio
    assert "analysisBlockingDetails" in studio
    assert "legacy-xai-missing-list" in studio
    assert "저장 전에 확인할 항목" in studio
    assert "고치는 방법" in studio
    assert "이 문제 AI에게 묻기" in studio
    assert "기술 코드 보기" in studio
    assert "과거 시세 재생 검사" in studio
    assert "과거 시세 최소검증" not in studio


def test_strategy_studio_guided_start_is_level_independent_and_never_skips_safety() -> None:
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    for contract in [
        "처음 사용 · 5분 따라 만들기",
        '{t("현재 Level ")}{featureViewLevel}{t("을 그대로 유지합니다',
        "기본 NoahAI에 맡기기",
        "예제 전략으로 따라하기",
        "내 전략 가져오기",
        '{t("쉬운 질문 ")}{guidedQuestion + 1}/3',
        "최종 재검증 후 전략 버전 저장",
        "사용자 승인",
        "PAPER 전진검증 시작",
        "안내 초기화는 저장 전략·PAPER·거래·학습 데이터를 삭제하지 않습니다",
        "client.strategyMentor",
    ]:
        assert contract in studio
    assert "setFeatureViewLevel" not in studio[studio.index("function openGuidedTour"):studio.index("useEffect(refresh")]
    assert "strategy-guided-backdrop" in styles
    assert "strategy-guided-progress" in styles


def test_strategy_studio_assistant_receives_the_current_unsaved_analysis_summary() -> None:
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")

    explanation = (ROOT / "webui" / "src" / "strategyExplanation.ts").read_text(encoding="utf-8")
    assert "analysisAssistantPrompt" in studio
    assert "strategyExplanationPrompt(sourceAnalysis, name, service)" in studio
    # Same metadata contract now uses a bounded JSON snapshot plus actual rules,
    # rather than hard-coded prose fragments. Runtime round-trip has Node tests.
    for contract in ["source.kind", "analysis.ready_for_execution", "market_regime_suggestion",
                     "analysis.blocking_details", "rules:", "coverage:", "source_excerpts:"]:
        assert contract in explanation


def test_strategy_studio_user_declared_override_checkbox_has_dedicated_layout() -> None:
    styles = (ROOT / "webui" / "src" / "styles.css").read_text(encoding="utf-8")

    assert '.studio-editor .legacy-advanced-rule-editor > label.legacy-rule-override-confirm {' in styles
    assert '.legacy-rule-override-confirm > input[type="checkbox"]' in styles
    assert "grid-template-columns: 18px minmax(0, 1fr) auto" in styles
    assert "appearance: auto" in styles
    assert "width: 18px" in styles


def test_ai_custom_strategy_hub_flow_is_manual_and_documented_in_dashboard() -> None:
    studio = (ROOT / "webui" / "src" / "components" / "StrategyStudio.tsx").read_text(encoding="utf-8")
    payload = json.loads((ROOT / "docs" / "USER_MANUAL_SECTIONS.json").read_text(encoding="utf-8"))
    custom = next(section["content"] for section in payload["sections"] if section["id"] == "custom")

    for contract in [
        'const STRATEGY_HUB_URL = "https://daltrading.net/strategies"',
        "STRATEGY_HUB_GUIDE_URL",
        "STRATEGY_HUB_SUBMIT_URL",
        "STRATEGY_HUB_LIBRARY_URL",
        "전략 둘러보기",
        "내 전략 라이선스",
        "거래소·증권사와 시장국면은 직접 입력이 아니라 체크박스로 선택합니다",
        "브라우저에 로그인되어 있지 않으면 로그인한 뒤 자동으로 라이선스 화면으로 돌아옵니다",
        "내 전략 제출은 자동 업로드가 아닙니다",
        "패키지 내보내기",
        "허브에 제출",
    ]:
        assert contract in studio
    for contract in [
        "[무료 전략 허브 — 회원 제출·저장·다운로드]",
        "자동 업로드가 아닙니다",
        "가격 0인 취득 기록",
        "영구·비독점 실행 라이선스",
        "내 전략 라이선스",
        "자기신고 승률·수익률은 랭킹 증거로 사용하지 않습니다",
        "어떤 검증도 조작과 미래 손실을 100% 제거할 수 없습니다",
        "[무료 베타 이후 수익원과 블록체인 계획]",
    ]:
        assert contract in custom
    assert 'asset_class: service === "stock" ? "stock" : "crypto"' in studio


def test_stock_info_uses_existing_broker_analysis_and_trend_keeps_public_market_quotes() -> None:
    api = (ROOT / "webui" / "src" / "api.ts").read_text(encoding="utf-8")
    workspaces = (ROOT / "webui" / "src" / "components" / "LegacyFeatureWorkspaces.tsx").read_text(encoding="utf-8")

    assert "stockOverview" in api
    assert 'client.stockOverview(symbols)' in workspaces
    assert 'runtimeCommand("stocks.analyze", broker, false, normalized)' in workspaces
    assert "stockSuggestions" in api
    assert "client.stockSuggestions" in workspaces
    assert "⭐ 즐겨찾기" in workspaces
    assert "최근검색" in workspaces
    assert "자동완성" in workspaces
    assert "자동매매 추가" in workspaces
    assert "네이버 금융 공개 시세(계좌·주문과 분리)" in workspaces
    assert 'row.volumeValue != null ? numberText(row.volumeValue, 0) : "미제공"' in workspaces
    assert 'stockAnalysis.volume == null || !Number.isFinite(Number(stockAnalysis.volume)) ? "미제공"' in workspaces
    assert '["005930", "000660", "035420", "035720", "005380", "373220"]' in workspaces


def test_exit_button_routes_through_safe_shutdown_ipc() -> None:
    app = (ROOT / "webui" / "src" / "App.tsx").read_text(encoding="utf-8")
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    preload = (ROOT / "webui" / "electron" / "preload.cjs").read_text(encoding="utf-8")

    assert "requestClose" in app
    assert "window:request-close" in main
    assert "requestSafeGatewayShutdown" in main
    assert "requestClose" in preload


def test_windows_safe_shutdown_terminates_the_pyinstaller_engine_tree() -> None:
    main = (ROOT / "webui" / "electron" / "main.cjs").read_text(encoding="utf-8")
    shutdown = main.split("async function requestSafeGatewayShutdown", 1)[1].split("function createWindow", 1)[0]

    assert 'const { spawn, spawnSync } = require("node:child_process");' in main
    assert 'spawnSync("taskkill.exe", ["/PID", String(pid), "/T", "/F"]' in main
    assert 'spawnSync("taskkill.exe", ["/IM", "NoahAIEngine.exe", "/T", "/F"]' in main
    assert shutdown.index("payload.safe_to_exit") < shutdown.index("stopGatewayAfterHandshake();")


def test_web_migration_docs_block_release_until_legacy_ui_parity() -> None:
    status = (ROOT / "docs" / "WEB_UI_MIGRATION_STATUS_v3.9.1.0.md").read_text(encoding="utf-8")
    checklist = (ROOT / "docs" / "DEPLOY_CHECKLIST.md").read_text(encoding="utf-8")

    assert "기존 UI/UX 및 기능 흐름 재작업 중" in status
    assert "배포 불가" in status
    assert "legacy_visual_parity" in status
    assert "legacy_flow_parity" in status
    assert "기존 v3.9.0.10 `AITrading.exe`/`python3 main.py` UI의 기술 이전" in checklist
    assert "React 화면이 열린다" in checklist
