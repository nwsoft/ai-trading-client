import { useEffect, useMemo, useState } from "react";

import { createGatewayClient } from "./api";
import { LegacyTradingLogWorkspace, LifeFinance } from "./components/Operations";
import { SettingsCenter } from "./components/SettingsCenter";
import { StrategyStudio, type StrategyAssistantDraft } from "./components/StrategyStudio";
import { LoginHelpScreen, LoginScreen } from "./components/LoginScreen";
import { AssistantWorkspace, ManualCenter } from "./components/AssistantWorkspace";
import { UpdateCenter } from "./components/UpdateCenter";
import { FinancialIntelligenceWorkspace } from "./components/FinancialIntelligenceWorkspace";
import { PortfolioWorkspace } from "./components/PortfolioWorkspace";
import { AlphaArenaWorkspace } from "./components/AlphaArenaWorkspace";
import { LifeFinanceAdvanced } from "./components/LifeFinanceAdvanced";
import { AIAnalystWorkspace } from "./components/AIAnalystWorkspace";
import { AIAnalystScenarioWorkspace } from "./components/AIAnalystScenarioWorkspace";
import { AssetInfoWorkspace, LegacyAILearningWorkspace, LegacyAIReportWorkspace, MarketTrendWorkspace, SourceWorkspace } from "./components/LegacyFeatureWorkspaces";
import { AppIcon, type AppIconName } from "./components/AppIcon";
import { TradingStatisticsWorkspace } from "./components/TradingStatisticsWorkspace";
import { featureSurface } from "./featureSurfaces";
import type { FeatureInventory, PlatformContract, RuntimeSnapshot } from "./types";
import type { SessionSnapshot } from "./types";
import { startSequentialPoll } from "./sequentialPoll";
import { CRYPTO_SOURCES, STOCK_SOURCES } from "./venueSources";
const SERVICE_ICONS: Record<string, AppIconName> = {
  blockchain: "blockchain",
  stock: "stock",
  portfolio: "portfolio",
  personal_finance: "finance",
  ai_analyst: "analyst",
};

const ASSISTANT_FEATURE_BY_SERVICE: Record<string, string> = {
  blockchain: "blockchain.ai_assistant",
  stock: "stock.ai_assistant",
  ai_analyst: "ai_analyst.assistant",
};

function runtimeForService(runtime: RuntimeSnapshot | null, service: string): RuntimeSnapshot | null {
  if (!runtime || !["blockchain", "stock"].includes(service)) return runtime;
  const allowed = service === "stock" ? STOCK_SOURCES : CRYPTO_SOURCES;
  const enabled = (runtime.enabled_sources_by_service?.[service]
    ?? runtime.enabled_sources.filter((source) => allowed.includes(source)))
    .filter((source) => allowed.includes(source));
  const requested = runtime.selected_sources?.[service] ?? "";
  const selected = enabled.includes(requested) ? requested : enabled[0] ?? null;
  return {
    ...runtime,
    service,
    selected_source: selected,
    enabled_sources: enabled,
    running_sources: runtime.running_sources_by_service?.[service]
      ?? runtime.running_sources.filter((source) => allowed.includes(source)),
  };
}

function userLabel(session: SessionSnapshot | null): string {
  const user = session?.user ?? {};
  const id = String(user.id || session?.account || "사용자").trim();
  const rawGrade = String(user.user_grade || "프리미엄").trim().toLowerCase();
  const gradeLabels: Record<string, string> = {
    premium: "프리미엄",
    pro: "프리미엄",
    pro_coin: "프리미엄",
    pro_stock: "프리미엄",
    referral: "레퍼럴",
    free: "무료",
    basic: "일반",
  };
  const grade = gradeLabels[rawGrade] ?? String(user.user_grade || "프리미엄").replace(/_/g, " ");
  return `${id} | ${grade}`;
}

function sourceScopeLabel(runtime: RuntimeSnapshot | null, activeService: string, selectedSource = ""): string {
  runtime = runtimeForService(runtime, activeService);
  const scope = runtime?.enabled_sources ?? [];
  const selectedKey = String(selectedSource || runtime?.selected_source || "").toLowerCase();
  const selected = scope.includes(selectedKey) ? selectedKey.toUpperCase() : "미선택";
  const noun = activeService === "stock" ? "증권사" : "거래소";
  return `${noun}: ${scope.length}곳 · 기준 ${selected}`;
}

function legacyStatusLabel(runtime: RuntimeSnapshot | null, selectedExchange: string, now: Date): string {
  // v3.9.0.10 정본의 get_status_info() 계약을 그대로 유지한다.
  // 하단은 제품 정체성·운영 모드·기준 거래소·현재 시각을 보여 주는 곳이며,
  // 활성 source 수나 워커 수를 새 문구로 재해석하지 않는다.
  const mode = runtime?.running_sources?.length ? "AUTO" : "MANUAL";
  const exchange = String(
    selectedExchange
      || runtime?.selected_sources?.blockchain
      || runtime?.selected_source
      || "binance",
  ).toUpperCase();
  const time = [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
  return `NoahAI-AI 금융 동반자 | MODE ${mode} | EXCHANGE ${exchange} | TIME ${time}`;
}

const AUXILIARY_SURFACE = new URLSearchParams(window.location.search).get("surface");

function applyDisplaySettings(fields: Array<{ path: string; value: unknown }>) {
  const values = Object.fromEntries(fields.map((field) => [field.path, field.value]));
  window.noahAI?.updater?.configure({
    enabled: values["ui_settings.auto_update_enabled"] !== false,
    intervalHours: Number(values["ui_settings.auto_update_check_interval_hours"] ?? 6),
    autoDownload: values["ui_settings.auto_update_auto_download"] === true,
    autoInstallOnAppQuit: values["ui_settings.auto_update_auto_apply_on_exit"] === true,
  }).catch(() => undefined);
  const displayPreset = String(values["ui_settings.display_preset"] ?? "display_standard");
  const zoom = displayPreset === "display_extra_large" ? 1.25 : displayPreset === "display_large" ? 1.12 : 1;
  if (window.noahAI?.window?.applyDisplayPreferences) {
    window.noahAI.window.applyDisplayPreferences({
      displayPreset,
      alwaysOnTop: Boolean(values["ui_settings.always_on_top"]),
    }).catch(() => undefined);
  } else {
    // 브라우저 개발 화면에서도 글자·로그·메뉴얼을 같은 비율로 검증한다.
    (document.documentElement.style as CSSStyleDeclaration & { zoom?: string }).zoom = String(zoom);
  }
}

function DesktopApp() {
  const client = useMemo(() => createGatewayClient(), []);
  const [platform, setPlatform] = useState<PlatformContract | null>(null);
  const [session, setSession] = useState<SessionSnapshot | null>(null);
  const [features, setFeatures] = useState<FeatureInventory | null>(null);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [selectedSources, setSelectedSources] = useState<Record<"blockchain" | "stock", string>>({
    blockchain: "binance",
    stock: "",
  });
  const [activeService, setActiveService] = useState("blockchain");
  const [activeFeature, setActiveFeature] = useState("blockchain.logs");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualInitialTab, setManualInitialTab] = useState("intro");
  const [assistantQuestion, setAssistantQuestion] = useState("");
  const [assistantService, setAssistantService] = useState("blockchain");
  const [assistantSettingsSection, setAssistantSettingsSection] = useState("");
  const [assistantReturnTarget, setAssistantReturnTarget] = useState<{ service: "blockchain" | "stock"; feature: string } | null>(null);
  const [strategyAssistantDraft, setStrategyAssistantDraft] = useState<StrategyAssistantDraft | null>(null);
  const [visitedStrategyStudios, setVisitedStrategyStudios] = useState<Record<"blockchain" | "stock", boolean>>({ blockchain: false, stock: false });
  const [lifeAssistantRequest, setLifeAssistantRequest] = useState(0);
  const [alphaArenaEnabled, setAlphaArenaEnabled] = useState(false);
  const [alphaArenaRunning, setAlphaArenaRunning] = useState(false);
  const [alphaStopBusy, setAlphaStopBusy] = useState(false);
  useEffect(() => {
    if (!session?.authenticated) { setAlphaArenaRunning(false); return; }
    return startSequentialPoll(() => client.alphaArena().then((data) => setAlphaArenaRunning(Boolean(data.running))).catch(() => undefined), 5000);
  }, [client, session?.authenticated, session?.account]);
  const [aiRecord, setAiRecord] = useState("AI 실행 기록 없음");
  const [statusClock, setStatusClock] = useState(() => new Date());
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const selected = features?.services.find((service) => service.id === activeService);
  const feature = selected?.features.find((item) => item.id === activeFeature) ?? selected?.features[0];
  const serviceRuntime = runtimeForService(runtime, activeService);
  const activeSurface = featureSurface(feature?.id);
  const assistantContextKey = `${assistantService}:${assistantSettingsSection}`;
  const [visitedAssistants, setVisitedAssistants] = useState<Record<string, { service: string; section: string }>>({});
  useEffect(() => { setVisitedAssistants({}); }, [session?.account, session?.authenticated]);
  useEffect(() => {
    if (activeSurface === "assistant" && session?.authenticated) {
      setVisitedAssistants((current) => current[assistantContextKey] ? current : {
        ...current, [assistantContextKey]: { service: assistantService, section: assistantSettingsSection },
      });
    }
  }, [activeSurface, assistantContextKey, assistantService, assistantSettingsSection, session?.account, session?.authenticated]);
  const activeSourceTabs = ["blockchain", "stock"].includes(activeService) ? serviceRuntime?.enabled_sources ?? [] : [];
  const requestedChartSource = activeService === "stock" ? selectedSources.stock : selectedSources.blockchain;
  const chartSource = activeSourceTabs.includes(requestedChartSource) ? requestedChartSource : activeSourceTabs[0] ?? "";

  useEffect(() => {
    if (activeSurface !== "strategy" || !["blockchain", "stock"].includes(activeService)) return;
    const strategyService = activeService as "blockchain" | "stock";
    setVisitedStrategyStudios((current) => current[strategyService] ? current : { ...current, [strategyService]: true });
  }, [activeService, activeSurface]);

  function applyRuntimeSnapshot(nextRuntime: RuntimeSnapshot) {
    setRuntime(nextRuntime);
    const blockchainRuntime = runtimeForService(nextRuntime, "blockchain");
    const stockRuntime = runtimeForService(nextRuntime, "stock");
    setSelectedSources((current) => ({
      blockchain: blockchainRuntime?.enabled_sources.includes(current.blockchain)
        ? current.blockchain
        : blockchainRuntime?.selected_source ?? "",
      stock: stockRuntime?.enabled_sources.includes(current.stock)
        ? current.stock
        : stockRuntime?.selected_source ?? "",
    }));
  }

  async function refreshRuntimeFromSettings() {
    try {
      const [nextRuntime, nextSettings] = await Promise.all([client.runtime(), client.settings()]);
      applyRuntimeSnapshot(nextRuntime);
      applyDisplaySettings(nextSettings.fields);
      setError("");
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : "런타임 상태를 다시 불러오지 못했습니다.";
      setError(`설정 파일 저장은 완료됐지만 화면 상태 새로고침에 실패했습니다. 앱을 다시 열어 반영 상태를 확인하세요. · ${detail}`);
      throw reason;
    }
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([client.platform(), client.session()])
      .then(([nextPlatform, nextSession]) => {
        if (!alive) return;
        setPlatform(nextPlatform); setSession(nextSession);
        if (!nextSession.authenticated) {
          setFeatures(null); setRuntime(null); setError("");
        }
      })
      .catch((reason: unknown) => alive && setError(reason instanceof Error ? reason.message : "Web UI 초기화에 실패했습니다."))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [client]);

  useEffect(() => {
    if (!session?.authenticated) return;
    let alive = true;
    setLoading(true);
    Promise.all([client.features(), client.runtime()])
      .then(([nextFeatures, nextRuntime]) => {
        if (!alive) return;
        setFeatures(nextFeatures); applyRuntimeSnapshot(nextRuntime); setError("");
        client.settings()
          .then((nextSettings) => {
            if (!alive) return;
            setAlphaArenaEnabled(Boolean(nextSettings.fields.find((field) => field.path === "alpha_arena.enabled")?.value));
            applyDisplaySettings(nextSettings.fields);
          })
          .catch(() => alive && setAlphaArenaEnabled(false));
      })
      .catch((reason: unknown) => alive && setError(reason instanceof Error ? reason.message : "운영 기능을 불러오지 못했습니다."))
      .finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [client, session?.authenticated]);

  async function refreshAiRecord() {
    try {
      const payload = await client.auditExport();
      const records = Array.isArray(payload.records) ? payload.records : [];
      const aiEventPrefixes = ["assistant.", "strategy.", "alpha_arena.", "financial_intelligence."];
      const latest = [...records].reverse().find((record) => {
        const event = String(record?.event ?? "");
        return aiEventPrefixes.some((prefix) => event.startsWith(prefix));
      });
      if (!latest) { setAiRecord("AI 실행 기록 없음"); return; }
      const at = String(latest.at ?? "").replace("T", " ").replace(/\.\d+Z$/, "Z");
      setAiRecord(`${at ? `${at} · ` : ""}${String(latest.event ?? "AI 실행")}`);
    } catch (_) {
      setAiRecord("AI 실행 기록 조회 실패");
    }
  }

  useEffect(() => {
    if (session?.authenticated) void refreshAiRecord();
  }, [session?.authenticated]);

  useEffect(() => {
    if (!session?.authenticated) return;
    const timer = window.setInterval(() => setStatusClock(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, [session?.authenticated]);

  useEffect(() => {
    if (!session?.authenticated) return;
    let alive = true;
    const refresh = () => client.runtime()
      .then((nextRuntime) => { if (alive) applyRuntimeSnapshot(nextRuntime); })
      .catch(() => { /* Preserve the last known state; the next poll retries. */ });
    const stop = startSequentialPoll(refresh, 2_000, { immediate: false });
    return () => { alive = false; stop(); };
  }, [client, session?.authenticated]);

  useEffect(() => {
    const mode = session?.authenticated ? "dashboard" : "login";
    const displayVersion = platform?.release_version || "3.9.1.41";
    document.title = session?.authenticated ? `Noah AI Client - 대시보드 Beta v${displayVersion}` : "NoahAI Finance Decision OS - 로그인";
    document.body.classList.toggle("dashboard-surface", Boolean(session?.authenticated));
    window.noahAI?.window?.setMode(mode).catch(() => undefined);
    return () => document.body.classList.remove("dashboard-surface");
  }, [session?.authenticated, platform?.release_version]);

  function changeChartSource(value: string) {
    if (activeService === "stock") {
      if (STOCK_SOURCES.includes(value)) setSelectedSources((current) => ({ ...current, stock: value }));
      return;
    }
    if (activeService === "blockchain" && CRYPTO_SOURCES.includes(value)) {
      setSelectedSources((current) => ({ ...current, blockchain: value }));
    }
  }

  function selectService(serviceId: string) {
    const service = features?.services.find((item) => item.id === serviceId);
    setActiveService(serviceId); setActiveFeature(service?.features[0]?.id ?? ""); setAssistantService(serviceId);
  }

  function selectSourceTab(source: string) {
    changeChartSource(source);
    if (activeService === "stock") {
      setActiveFeature("stock.source_workspaces");
      return;
    }
    setActiveFeature("blockchain.source_workspaces");
  }

  function openAssistant(question: string, service = activeService, settingsSection = "") {
    setAssistantReturnTarget(null);
    setAssistantQuestion(question);
    setAssistantService(service);
    setAssistantSettingsSection(service === "settings" ? settingsSection : "");
    if (service === "personal_finance") {
      // 생활금융 AI 상담은 상위 정보구조에 임의의 숨은 탭을 만들지 않고,
      // 레거시와 같은 생활금융 서비스 내부 탭으로 이동한다.
      setActiveService("personal_finance");
      setActiveFeature("personal_finance.service");
      setLifeAssistantRequest((value) => value + 1);
    } else if (service === "portfolio") {
      // 자산 통합에는 레거시 상위 AI 어시스턴트 탭이 없다. 전 자산 문맥을
      // 다루는 AI 애널리스트 어시스턴트가 정식 진입점이다.
      setActiveService("ai_analyst");
      setActiveFeature("ai_analyst.assistant");
    } else {
      const nextService = ASSISTANT_FEATURE_BY_SERVICE[service] ? service : "blockchain";
      setActiveService(nextService);
      setActiveFeature(ASSISTANT_FEATURE_BY_SERVICE[nextService]);
    }
    setSettingsOpen(false);
    setManualOpen(false);
  }

  function openStrategyAssistant(question: string, strategyService: "blockchain" | "stock") {
    setAssistantQuestion(question);
    setAssistantService("ai_custom");
    setAssistantSettingsSection("");
    setAssistantReturnTarget({ service: strategyService, feature: `${strategyService}.ai_custom` });
    setActiveService(strategyService);
    setActiveFeature(ASSISTANT_FEATURE_BY_SERVICE[strategyService]);
    setSettingsOpen(false);
    setManualOpen(false);
  }

  function returnFromStrategyAssistant() {
    if (!assistantReturnTarget) return;
    setActiveService(assistantReturnTarget.service);
    setActiveFeature(assistantReturnTarget.feature);
    setAssistantService(assistantReturnTarget.service);
    setAssistantQuestion("");
    setAssistantReturnTarget(null);
  }

  function sendAssistantAnswerToStrategy(answer: string) {
    if (!assistantReturnTarget || !answer.trim()) return;
    setStrategyAssistantDraft({ id: Date.now(), service: assistantReturnTarget.service, text: answer.trim() });
    returnFromStrategyAssistant();
  }

  function openManualTarget(service: string, featureId: string) {
    const serviceContract = features?.services.find((item) => item.id === service);
    const target = serviceContract?.features.find((item) => item.id === featureId);
    if (!target) { setError(`메뉴얼 연결 대상 화면을 찾지 못했습니다: ${featureId}`); return; }
    setActiveService(service);
    setActiveFeature(target.id);
    setAssistantService(service);
    setManualOpen(false);
  }

  function openManual(tab = "intro") {
    setManualInitialTab(tab);
    setManualOpen(true);
  }

  async function exportAudit() {
    try {
      const payload = await client.auditExport();
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `NoahAI-audit-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click(); URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "감사 기록 내보내기에 실패했습니다.");
    }
  }

  if (session && !session.authenticated) return <LoginScreen client={client} onSuccess={(nextSession) => setSession(nextSession)} />;

  // Do not render the parity-failure surface during the short interval between
  // session restoration and feature-inventory loading.  That surface is only
  // for a genuinely unmapped feature, not an application bootstrap state.
  if (session?.authenticated && loading && !features) {
    return <div className="app-shell legacy-dashboard-shell legacy-bootstrap-state" role="status">운영 화면을 불러오는 중입니다.</div>;
  }

  return <div className="app-shell legacy-dashboard-shell">
    <header className="legacy-topbar">
      <div className="legacy-identity">
        <span className="legacy-user-chip">{userLabel(session)}</span>
        <span className="legacy-source-chip">{sourceScopeLabel(runtime, activeService, chartSource)}</span>
      </div>
      <nav className="service-nav" aria-label="주요 서비스">
        {features?.services.map((service) => (
          <button className={`${service.id === activeService ? "active" : ""} service-${service.id}`} key={service.id} onClick={() => selectService(service.id)} type="button">
            <AppIcon name={SERVICE_ICONS[service.id] ?? "portfolio"} />
            {service.label}
          </button>
        ))}
      </nav>
      <div className="top-actions">
        <button className="primary-button legacy-action-button" type="button" onClick={() => openManual()}><AppIcon name="manual" />메뉴얼</button>
        <button className="primary-button legacy-action-button" type="button" onClick={() => setSettingsOpen(true)}><AppIcon name="settings" />설정</button>
        <button className="danger-button legacy-exit-button" type="button" onClick={() => {
          if (!window.confirm("거래 워커와 기록을 안전하게 정리한 뒤 NoahAI를 종료할까요?")) return;
          window.noahAI?.window?.requestClose().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "안전 종료 요청에 실패했습니다."));
        }}><AppIcon name="power" />종료</button>
      </div>
    </header>
    <section className="legacy-content-frame">
      <nav className="feature-nav" key={activeService} aria-label={`${selected?.label ?? "서비스"} 기능`}>
        <div className="feature-tab-strip" role="group" aria-label={`${selected?.label ?? "서비스"} 세부 기능`}>
          {selected?.features.filter((item) => !item.id.endsWith("source_workspaces") && (item.id !== "blockchain.alpha_arena" || alphaArenaEnabled || alphaArenaRunning)).map((item) => <button className={item.id === feature?.id ? "active" : ""} key={item.id} onClick={() => { setActiveFeature(item.id); if (item.id.endsWith("ai_assistant") || item.id === "ai_analyst.assistant") setAssistantService(activeService); }} type="button">{item.label}</button>)}
        </div>
        {["blockchain", "stock"].includes(activeService) && <div className="source-tab-strip" role="group" aria-label={activeService === "stock" ? "증권사 선택" : "거래소 선택"}>
          <span className="source-tab-label">{activeSurface === "alpha_arena" ? "일반 거래소 화면으로 이동" : activeService === "stock" ? "증권사" : "거래소"}</span>
          {activeSourceTabs.map((source) => (
            <button className={`source-tab ${feature?.id.endsWith("source_workspaces") && chartSource === source ? "active" : ""}`} key={source} onClick={() => selectSourceTab(source)} type="button">{source.toUpperCase()}</button>
          ))}
          {!activeSourceTabs.length && <span className="source-empty-note">설정에서 사용할 {activeService === "stock" ? "증권사" : "거래소"}를 선택하세요.</span>}
        </div>}
      </nav>
      <main>{alphaArenaRunning && <div className="inline-notice arena-running-banner" role="status"><b>AlphaArena · Binance PAPER 판단 실험 실행 중</b><span>현재 화면의 거래소 선택과 별개입니다.</span><button type="button" disabled={alphaStopBusy} onClick={async () => { setAlphaStopBusy(true); try { await client.alphaArenaCommand("stop", false); setAlphaArenaRunning(false); } catch (reason) { setError(reason instanceof Error ? reason.message : "AlphaArena 정지 실패"); } finally { setAlphaStopBusy(false); } }}>AlphaArena 정지</button></div>}{error && <div className="error-banner"><b>Gateway 연결 확인</b><span>{error}</span><button className="secondary-button" type="button" onClick={() => window.location.reload()}>전체 다시 시도</button></div>}
      {activeSurface === "market_trend" && <MarketTrendWorkspace client={client} service={activeService as "blockchain" | "stock"} source={chartSource} onAskAssistant={(question) => openAssistant(question, activeService)} />}
      {activeSurface === "trading_log" && <LegacyTradingLogWorkspace client={client} runtime={serviceRuntime} service={activeService} onOpenManual={() => openManual()} onAskAssistant={(question) => openAssistant(question, activeService)} onRuntimeChanged={refreshRuntimeFromSettings} />}
      {(["blockchain", "stock"] as const).map((strategyService) => {
        const visible = activeSurface === "strategy" && activeService === strategyService;
        if (!visible && !visitedStrategyStudios[strategyService]) return null;
        return <div className="strategy-studio-keepalive" hidden={!visible} key={strategyService}><StrategyStudio client={client} service={strategyService} source={selectedSources[strategyService]} onAskAssistant={(question) => openStrategyAssistant(question, strategyService)} onOpenSettings={() => setSettingsOpen(true)} assistantDraft={strategyAssistantDraft?.service === strategyService ? strategyAssistantDraft : null} onAssistantDraftConsumed={() => setStrategyAssistantDraft(null)} /></div>;
      })}
      {activeSurface === "ai_learning" && <LegacyAILearningWorkspace client={client} service={activeService as "blockchain" | "stock"} source={chartSource} sources={activeSourceTabs} />}
      {activeSurface === "ai_report" && <LegacyAIReportWorkspace client={client} service={activeService as "blockchain" | "stock"} source={chartSource} sources={activeSourceTabs} onAskAssistant={(question) => openAssistant(question, activeService)} />}
      {Object.entries(visitedAssistants).map(([contextKey, context]) => <div key={`${session?.account}:${contextKey}`} hidden={activeSurface !== "assistant" || contextKey !== assistantContextKey}>
        <AssistantWorkspace client={client} service={context.service} initialQuestion={contextKey === assistantContextKey ? assistantQuestion : ""} settingsSection={context.service === "settings" ? context.section : ""} onOpenSettings={() => setSettingsOpen(true)} onChartAnalysis={() => setActiveFeature(activeService === "stock" ? "stock.info" : activeService === "ai_analyst" ? "ai_analyst.workspace" : "blockchain.coin_info")} onReturn={assistantReturnTarget ? returnFromStrategyAssistant : undefined} returnLabel={assistantReturnTarget ? "전략 스튜디오로 돌아가기 · 입력 유지" : undefined} onSendToStrategy={assistantReturnTarget ? sendAssistantAnswerToStrategy : undefined} />
      </div>)}
      {activeSurface === "ai_analyst" && <AIAnalystWorkspace client={client} onOpenAssistant={(question = "") => openAssistant(question, "ai_analyst")} onOpenSummary={() => setActiveFeature("ai_analyst.summary")} onOpenScenario={() => setActiveFeature("ai_analyst.scenario")} />}
      {activeSurface === "ai_analyst_scenario" && <AIAnalystScenarioWorkspace client={client} />}
      {activeSurface === "financial_intelligence" && <FinancialIntelligenceWorkspace client={client} service={activeService === "stock" ? "stock" : activeService === "ai_analyst" ? "ai_analyst" : "blockchain"} summaryOnly={feature?.id === "ai_analyst.summary"} onAskAssistant={(question) => openAssistant(question, activeService)} />}
      {activeSurface === "portfolio" && <PortfolioWorkspace client={client} featureId={feature?.id ?? "portfolio.insights"} enabledSources={runtime?.enabled_sources ?? []} credentialStatus={runtime?.credential_status ?? {}} />}
      {activeSurface === "alpha_arena" && <AlphaArenaWorkspace client={client} />}
      {activeSurface === "life_basic" && <LifeFinance client={client} view={feature?.id ?? "personal_finance.service"} assistantRequest={lifeAssistantRequest} initialQuestion={assistantQuestion} onOpenSettings={() => setSettingsOpen(true)} />}
      {activeSurface === "life_advanced" && <LifeFinanceAdvanced client={client} featureId={feature?.id ?? "personal_finance.security"} />}
      {activeSurface === "asset_info" && <AssetInfoWorkspace client={client} service={activeService as "blockchain" | "stock"} source={chartSource} enabledSources={serviceRuntime?.enabled_sources ?? []} />}
      {activeSurface === "source_workspace" && (chartSource ? <SourceWorkspace key={`${activeService}:${chartSource}`} client={client} runtime={serviceRuntime} service={activeService as "blockchain" | "stock"} source={chartSource} onOpenManual={() => openManual()} onOpenSettings={() => setSettingsOpen(true)} onRuntimeChanged={refreshRuntimeFromSettings} /> : <section className="panel source-selection-required"><h2>{activeService === "stock" ? "사용할 증권사가 선택되지 않았습니다." : "사용할 거래소가 선택되지 않았습니다."}</h2><p>설정 → 거래소 선택에서 분석에 사용할 대상을 선택하고 저장하세요. 선택하지 않은 연결은 화면과 런타임에서 실행하지 않습니다.</p><button className="primary-button" type="button" onClick={() => setSettingsOpen(true)}>설정 열기</button></section>)}
      {activeSurface === "trading_statistics" && <TradingStatisticsWorkspace client={client} runtime={serviceRuntime} service={activeService as "blockchain" | "stock"} sources={activeSourceTabs} defaultSource={chartSource} />}
      {activeSurface === "unmapped" && <section className="panel parity-route-error" role="alert"><h2>1:1 화면 연결 오류</h2><p>{feature?.label ?? "선택 기능"}은 레거시 정본 전용 화면에 연결되지 않았습니다. 공용 대체 화면을 표시하지 않고 배포를 차단합니다.</p></section>}
      </main>
    </section>
    <footer className="statusbar legacy-statusbar">
      <span className="legacy-status-left">{legacyStatusLabel(runtime, chartSource, statusClock)}</span>
      <div className="legacy-release-update"><span className="legacy-release">{platform?.release_label ?? "v3.9.1.41"}</span><UpdateCenter client={client} accountScope={session?.account ?? ""} onOpenGuide={() => openManual("updates")} /></div>
      <div className="legacy-ai-summary"><span className="legacy-ai-record" title={aiRecord}>{aiRecord}</span><button className="legacy-record-button" type="button" onClick={() => void refreshAiRecord()}><AppIcon name="record" />기록</button></div>
    </footer>
    <SettingsCenter client={client} open={settingsOpen} onClose={() => setSettingsOpen(false)} onAskAssistant={(question, settingsSection) => openAssistant(question, "settings", settingsSection)} onOpenManual={() => { setSettingsOpen(false); openManual("settings"); }} onSettingsSaved={refreshRuntimeFromSettings} />
    {manualOpen && <ManualCenter client={client} initialTab={manualInitialTab} onClose={() => setManualOpen(false)} onAskAssistant={(question) => openAssistant(question, activeService)} onOpenSettings={() => { setManualOpen(false); setSettingsOpen(true); }} onNavigate={openManualTarget} />}
  </div>;
}

export default function App() {
  if (AUXILIARY_SURFACE === "login-help") return <LoginHelpScreen />;
  return <DesktopApp />;
}
