import { t } from '../i18n';
import { useEffect, useRef, useState } from "react";

import type { GatewayClient } from "../api";
import type { LifeFinanceSnapshot, LogSnapshot, RuntimeSnapshot, WorkspaceSnapshot } from "../types";
import { AssistantWorkspace } from "./AssistantWorkspace";
import { LifeFinanceAdvanced } from "./LifeFinanceAdvanced";
import { LogHelpDialog } from "./LogHelpDialog";
import { startSequentialPoll } from "../sequentialPoll";
import { sourcesForService, venueProfile } from "../venueSources";

function displayMoney(value: unknown, currency = "USDT") {
  const number = Number(value ?? 0);
  return `${number >= 0 ? "+" : ""}${number.toLocaleString(undefined, { maximumFractionDigits: 4 })}${currency === "KRW" ? "원" : " USDT"}`;
}

function allowedSourcesForService(service: string) {
  return sourcesForService(service);
}

function dashboardStatisticsMode(runtime: RuntimeSnapshot | null, service: string): "live" | "paper" {
  const allowed = allowedSourcesForService(service);
  const running = (runtime?.running_sources ?? []).filter((source) => allowed.includes(source));
  const configured = (runtime?.enabled_sources ?? []).filter((source) => allowed.includes(source));
  const relevant = running.length ? running : configured;
  return relevant.length > 0 && relevant.every(
    (source) => String(runtime?.execution_modes?.[source] ?? "").toLowerCase() === "paper",
  ) ? "paper" : "live";
}

export function LegacyTradingLogWorkspace({
  client,
  runtime,
  service,
  onOpenManual,
  onAskAssistant,
  onRuntimeChanged,
}: {
  client: GatewayClient;
  runtime: RuntimeSnapshot | null;
  service: string;
  onOpenManual: () => void;
  onAskAssistant: (question: string) => void;
  onRuntimeChanged: () => Promise<void> | void;
}) {
  const [logs, setLogs] = useState<LogSnapshot | null>(null);
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [accountPayload, setAccountPayload] = useState<Record<string, any> | null>(null);
  const [visibleLines, setVisibleLines] = useState<LogSnapshot["lines"]>([]);
  const [error, setError] = useState("");
  const [logLevel, setLogLevel] = useState("ALL");
  const [exchange, setExchange] = useState("ALL");
  const [category, setCategory] = useState("ALL");
  const [simpleOnly, setSimpleOnly] = useState(false);
  const [analysisOnly, setAnalysisOnly] = useState(false);
  const [hideInit, setHideInit] = useState(false);
  const [hideDebug, setHideDebug] = useState(false);
  const [hideSystem, setHideSystem] = useState(false);
  const [logHelpOpen, setLogHelpOpen] = useState(false);
  const [batchBusy, setBatchBusy] = useState(false);
  const [batchMessage, setBatchMessage] = useState("");
  const clearMarkerRef = useRef("");
  const logConsoleRef = useRef<HTMLDivElement | null>(null);
  const statisticsMode = dashboardStatisticsMode(runtime, service);

  function applyClearBoundary(lines: LogSnapshot["lines"]) {
    const marker = clearMarkerRef.current;
    if (!marker) return lines;
    const markerIndex = lines.map((line) => line.message).lastIndexOf(marker);
    return markerIndex >= 0 ? lines.slice(markerIndex + 1) : lines;
  }

  function refresh() {
    const accountSources = (runtime?.enabled_sources ?? []).filter((source) =>
      allowedSourcesForService(service).includes(source)
      && runtime?.credential_status?.[source],
    );
    Promise.all([
      client.logs(service as "blockchain" | "stock", "all", 100),
      client.workspace(service, `${service}.logs`, "", { statisticsPeriod: "today", statisticsMode }),
      statisticsMode === "live" && accountSources.length ? client.refreshAccounts(accountSources, false) : Promise.resolve(null),
    ]).then(([nextLogs, nextWorkspace, nextAccounts]) => {
      setLogs(nextLogs); setVisibleLines(applyClearBoundary(nextLogs.lines)); setWorkspace(nextWorkspace); setError("");
      setAccountPayload(nextAccounts);
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "대시보드 데이터를 불러오지 못했습니다."));
  }

  useEffect(() => {
    let alive = true;
    const loadLogs = () => client.logs(service as "blockchain" | "stock", "all", 100).then((nextLogs) => {
      if (!alive) return;
      setLogs(nextLogs); setVisibleLines(applyClearBoundary(nextLogs.lines)); setError("");
    }).catch((reason: unknown) => alive && setError(reason instanceof Error ? reason.message : "대시보드 데이터를 불러오지 못했습니다."));
    const loadWorkspace = () => client.workspace(service, `${service}.logs`, "", { statisticsPeriod: "today", statisticsMode }).then((nextWorkspace) => {
      if (alive) setWorkspace(nextWorkspace);
    }).catch((reason: unknown) => alive && setError(reason instanceof Error ? reason.message : "대시보드 데이터를 불러오지 못했습니다."));
    const stopLogs = startSequentialPoll(loadLogs, 1_000);
    const stopWorkspace = startSequentialPoll(loadWorkspace, 5_000);
    const accountSources = (runtime?.enabled_sources ?? []).filter((source) =>
      allowedSourcesForService(service).includes(source) && runtime?.credential_status?.[source],
    );
    const loadAccounts = () => statisticsMode === "live" && accountSources.length
      ? client.refreshAccounts(accountSources, false).then((next) => { if (alive) setAccountPayload(next); }).catch(() => {})
      : Promise.resolve();
    const stopAccounts = startSequentialPoll(loadAccounts, 7_000);
    return () => { alive = false; stopLogs(); stopWorkspace(); stopAccounts(); };
  }, [client, service, runtime?.enabled_sources, runtime?.credential_status, runtime?.execution_modes, runtime?.running_sources, statisticsMode]);

  const allowedSources = allowedSourcesForService(service);
  const runningModeSources = (runtime?.running_sources ?? []).filter((source) => allowedSources.includes(source));
  const configuredModeSources = (runtime?.enabled_sources ?? []).filter((source) => allowedSources.includes(source));
  const relevantModeSources = runningModeSources.length ? runningModeSources : configuredModeSources;
  const paperModeSourceCount = relevantModeSources.filter(
    (source) => String(runtime?.execution_modes?.[source] ?? "").toLowerCase() === "paper",
  ).length;
  const mixedExecutionModes = paperModeSourceCount > 0 && paperModeSourceCount < relevantModeSources.length;
  // The log itself is operational evidence, including credential and adapter
  // errors. Do not hide those rows based on the current settings snapshot.
  const filteredLines = visibleLines.filter((line) => {
    const text = `${line.source} ${line.message}`.toLowerCase();
    const selectedCategory = ({ 거래: "trade", 분석: "analysis", 학습: "learning", 시스템: "system" } as Record<string, string>)[category] ?? "";
    if (exchange !== "ALL" && String(line.exchange ?? "").toLowerCase() !== exchange.toLowerCase() && !text.includes(exchange.toLowerCase())) return false;
    if (logLevel !== "ALL" && String(line.level ?? "").toUpperCase() !== logLevel && !text.includes(logLevel.toLowerCase())) return false;
    if (category !== "ALL" && line.category !== selectedCategory) return false;
    if (hideInit && /(초기|init|생성 완료|로드 완료)/i.test(text)) return false;
    if (hideDebug && (line.level === "DEBUG" || /debug/i.test(text))) return false;
    if (hideSystem && (line.category === "system" || /(system|ex=global)/i.test(text))) return false;
    if (analysisOnly && line.category !== "analysis" && !/(분석|analysis|signal|rsi|macd|trend)/i.test(text)) return false;
    if (simpleOnly && !["trade", "analysis"].includes(String(line.category ?? "")) && !/(거래 시그널|거래 실행|포지션|분석 완료|\bsignal\b)/i.test(text)) return false;
    return true;
  });
  const trading = workspace?.trading;
  const requestedAccountSources = (runtime?.enabled_sources ?? []).filter((source) =>
    allowedSources.includes(source) && runtime?.credential_status?.[source],
  );
  const accountRows = Object.values((accountPayload?.sources ?? {}) as Record<string, any>);
  const successfulAccountRows = accountRows.filter(
    (account) => account && String(account.status ?? "") === "success",
  );
  const actualPositionCount = accountRows.reduce((sum, account) => {
    if (!account || String(account.status ?? "") !== "success") return sum;
    return sum + (Array.isArray(account.positions) ? account.positions.length : 0);
  }, 0);
  // Do not present a partial multi-venue account refresh as the total.
  const accountPositionsAvailable = requestedAccountSources.length > 0
    && successfulAccountRows.length === requestedAccountSources.length;
  const openPositionCount = statisticsMode === "paper"
    ? Number(workspace?.paper_positions?.length ?? trading?.open_position_count ?? 0)
    : accountPositionsAvailable ? actualPositionCount : Number(trading?.open_position_count ?? 0);
  const primaryCurrency = service === "stock" ? "KRW" : "USDT";
  const pnl = Number(trading?.pnl_by_currency?.[primaryCurrency] ?? 0);
  const reconciledCount = Number(trading?.reconciled_closed_count ?? 0);
  const confirmedMetricsAvailable = statisticsMode === "paper" || reconciledCount > 0;
  const pnlCurrencies = Object.entries(trading?.pnl_by_currency ?? {}).filter(([, value]) => Number.isFinite(Number(value)));
  const pnlLabel = !confirmedMetricsAvailable
    ? "대조 전"
    : pnlCurrencies.length
      ? pnlCurrencies.map(([currency, value]) => displayMoney(value, currency)).join(" · ")
      : displayMoney(0, primaryCurrency);
  const winRateLabel = confirmedMetricsAvailable
    ? `${Number(trading?.win_rate ?? 0).toFixed(2)}%`
    : "대조 전";
  const runningCount = runtime?.running_sources.filter((source) => allowedSources.includes(source)).length ?? 0;
  // 레거시 운영 현황의 분모는 현재 실행 목록이 아니라 화면에서 지원하는
  // 전체 source 수다. 설정이 하나도 없을 때도 블록체인 0/6, 증권 0/4로
  // 표시해야 "지원 없음"과 "연결 전"을 혼동하지 않는다.
  const enabledCount = allowedSources.length;
  const configuredCount = allowedSources.filter((source) => runtime?.credential_status?.[source]).length;
  const startableSources = (runtime?.enabled_sources ?? []).filter(
    (source) => allowedSources.includes(source)
      && runtime?.credential_status?.[source]
      && !runtime?.running_sources.includes(source)
      && (runtime?.live_trading !== true || Boolean(venueProfile(source)?.live_supported ?? true)),
  );
  const stoppableSources = (runtime?.running_sources ?? []).filter((source) => allowedSources.includes(source));
  const sourceNoun = service === "stock" ? "증권사" : "거래소";
  const alertLevel = error ? "위험" : configuredCount === 0 ? "주의" : runningCount === 0 ? "주의" : "정상";
  const alertText = error
    ? `• ${error}`
    : configuredCount === 0
      ? `• API 키가 설정되지 않았습니다. 설정 → ${sourceNoun} API에서 연결한 뒤 잔고·포지션 조회를 시작하세요. 미설정 상태에서는 계좌 조회를 실행하지 않습니다.`
      : runningCount === 0
      ? `• 자율주행 실행 연계가 대기 상태입니다. ${sourceNoun} 실행 상태를 확인하세요.`
      : `• ${runningCount}/${enabledCount}개 ${sourceNoun} 엔진이 실행 중입니다.`;
  async function commandAll(action: "start" | "stop") {
    const targets = action === "start" ? startableSources : stoppableSources;
    if (!targets.length) {
      setBatchMessage(action === "start" ? `시작할 설정 완료 ${sourceNoun}가 없습니다.` : `실행 중인 ${sourceNoun}가 없습니다.`);
      return;
    }
    const live = action === "start" && runtime?.live_trading === true;
    const warning = live
      ? `LIVE 자동매매를 동시에 시작할까요?\n\n대상: ${targets.map((item) => item.toUpperCase()).join(", ")}\n실제 주문이 제출될 수 있습니다.`
      : `${targets.map((item) => item.toUpperCase()).join(", ")} ${action === "start" ? "자동매매를 동시에 시작" : "자동매매를 정지"}할까요?`;
    if (!window.confirm(warning)) return;
    setBatchBusy(true); setBatchMessage("");
    try {
      const results = await Promise.allSettled(targets.map((source) =>
        client.runtimeCommand(`trading.${action}`, source, false, "", live),
      ));
      const succeeded = results.filter((result) => result.status === "fulfilled").length;
      const failed = results.length - succeeded;
      setBatchMessage(`${action === "start" ? "시작" : "정지"} 완료 ${succeeded}곳${failed ? ` · 실패 ${failed}곳` : ""}`);
      try { await onRuntimeChanged(); }
      catch (_) { setBatchMessage((current) => `${current} · 화면 상태 자동 갱신 대기 중`); }
    } finally { setBatchBusy(false); }
  }
  useEffect(() => {
    const consoleElement = logConsoleRef.current;
    if (!consoleElement) return;
    consoleElement.scrollTop = consoleElement.scrollHeight;
  }, [filteredLines.length, service]);
  return <section className="legacy-log-workspace">
    <article className="legacy-log-card">
      <div className="legacy-log-filters">
        <label><input type="checkbox" checked={simpleOnly} onChange={(event) => { setSimpleOnly(event.target.checked); if (event.target.checked) setAnalysisOnly(false); }} />{t("거래 시그널만")}</label>
        <label><input type="checkbox" checked={analysisOnly} onChange={(event) => { setAnalysisOnly(event.target.checked); if (event.target.checked) setSimpleOnly(false); }} />{t("분석 과정만")}</label>
        <label><input type="checkbox" checked={!simpleOnly && !analysisOnly && !hideInit && !hideDebug && !hideSystem} onChange={() => { setSimpleOnly(false); setAnalysisOnly(false); setHideInit(false); setHideDebug(false); setHideSystem(false); }} />{t("전체 로그")}</label>
        <label><input type="checkbox" checked={hideInit} onChange={(event) => setHideInit(event.target.checked)} />{t("초기화 로그 숨김")}</label>
        <label><input type="checkbox" checked={hideDebug} onChange={(event) => setHideDebug(event.target.checked)} />{t("디버그 로그 숨김")}</label>
        <label><input type="checkbox" checked={hideSystem} onChange={(event) => setHideSystem(event.target.checked)} />{t("시스템 로그 숨김")}</label>
      </div>
      <div className="legacy-log-console" ref={logConsoleRef}>
        {filteredLines.map((line, index) => <div key={`${index}:${line.source}`}><code>{line.message}</code></div>)}
        {!logs && !error && <div className="empty-state">{t("실시간 로그를 불러오는 중입니다.")}</div>}
        {logs && !filteredLines.length && <div className="empty-state">{t("현재 필터에 표시할 로그가 없습니다.")}</div>}
      </div>
      <div className="legacy-log-toolbar">
        <button type="button" onClick={() => setLogHelpOpen(true)}>{t("로그도움말")}</button>
        <button type="button" onClick={() => { clearMarkerRef.current = visibleLines.at(-1)?.message ?? logs?.lines.at(-1)?.message ?? ""; setVisibleLines([]); }}>{t("로그지우기")}</button>
        <button type="button" onClick={() => { clearMarkerRef.current = ""; refresh(); }}>{t("새로고침")}</button>
        <span />
        <label>{t("로그 레벨:")}<select value={logLevel} onChange={(event) => setLogLevel(event.target.value)}><option value={"ALL"}>ALL</option><option value={"INFO"}>INFO</option><option value={"WARNING"}>WARNING</option><option value={"ERROR"}>ERROR</option></select></label>
        <label>{sourceNoun}:<select value={exchange} onChange={(event) => setExchange(event.target.value)}><option value={"ALL"}>ALL</option>{allowedSources.map((item) => <option key={item}>{item.toUpperCase()}</option>)}</select></label>
        <label>{t("카테고리:")}<select value={category} onChange={(event) => setCategory(event.target.value)}><option value={"ALL"}>ALL</option><option value={"거래"}>{t("거래")}</option><option value={"분석"}>{t("분석")}</option><option value={"학습"}>{t("학습")}</option><option value={"시스템"}>{t("시스템")}</option></select></label>
      </div>
    </article>
    <aside className="legacy-operations-column">
      <section><h3>{t("운영 KPI · 오늘 · ")}{statisticsMode.toUpperCase()}</h3><div className="legacy-kpi-grid"><div className="legacy-kpi-card"><span>{statisticsMode === "paper" ? t("가상 포지션") : t("현재 포지션")}</span><b>{openPositionCount}</b></div><div className="legacy-kpi-card"><span>{statisticsMode === "paper" ? t("가상 청산") : t("오늘 청산")}</span><b>{trading?.closed_count ?? 0}</b></div><div className="legacy-kpi-card"><span>{statisticsMode === "paper" ? t("가상 손익") : t("대조 완료 손익")}</span><b className={confirmedMetricsAvailable ? (pnl < 0 ? "negative" : "positive") : ""}>{pnlLabel}</b></div><div className="legacy-kpi-card"><span>{statisticsMode === "paper" ? t("가상 승률") : t("대조 완료 승률")}</span><b>{winRateLabel}</b></div></div></section>
      <section><h3>{t("거래 현황")}</h3><div className="legacy-operation-box"><b>{statisticsMode === "paper" ? t("현재 가상 원장 + 오늘 PAPER 청산") : t("현재 계좌 + 오늘 LIVE 청산")}</b><p>• {statisticsMode === "paper" ? t("현재 가상 포지션") : t("현재 계좌 포지션")}: {openPositionCount}{statisticsMode === "live" ? accountPositionsAvailable ? "" : requestedAccountSources.length ? " (일부 조회 실패 · 저장 원장 참고)" : " (계좌 조회 전 · 저장 원장 참고)" : ["temporarily_unavailable", "partial"].includes(String(workspace?.paper_positions_status ?? "")) ? " (일부 런타임 조회 지연)" : ""}<br />{t("• 오늘 ")}{statisticsMode === "paper" ? "가상 " : ""}{t("청산 수: ")}{trading?.closed_count ?? 0}{statisticsMode === "live" ? ` · 체결 대조 완료 ${Number(trading?.reconciled_closed_count ?? 0)}건 · 미확정 ${Number(trading?.unresolved_closed_count ?? 0)}건` : ""}<br />{t("• 오늘 ")}{statisticsMode === "paper" ? "가상 " : "체결 대조 완료 "}{t("순손익: ")}{pnlLabel}<br />{t("• 자동 거래 상태: ")}{runningCount ? t("실행 중") : `대기 (${runningCount}/${enabledCount} ${sourceNoun})`}{mixedExecutionModes ? <><br />{t("• 혼합 운용 중: 메인 KPI는 LIVE 기준이며 PAPER 상세는 거래 통계 탭에서 확인")}</> : null}</p></div></section>
      <section><h3>{sourceNoun}{t(" 일괄 실행")}</h3><div className="legacy-quick-actions"><button type="button" disabled={batchBusy || !startableSources.length} onClick={() => void commandAll("start")}>{batchBusy ? "처리 중…" : t("설정 대상 전체 시작")}</button><button type="button" disabled={batchBusy || !stoppableSources.length} onClick={() => void commandAll("stop")}>{t("실행 중 전체 정지")}</button></div>{batchMessage && <div className="legacy-operation-box"><p>{batchMessage}</p></div>}</section>
      <section><h3>Quick Actions</h3><div className="legacy-quick-actions"><button type="button" onClick={() => onAskAssistant("현재 설정과 거래 기록을 기준으로 AI 최적화 진단을 해줘. 변경은 하지 말고 근거와 위험을 설명해줘.")}>{t("AI 최적화 진단")}</button><button type="button" onClick={() => onAskAssistant("AI 최적화 적용 후보를 보여줘. 자동 적용하지 말고 현재값, 제안값, 근거와 위험을 비교해줘.")}>{t("AI 최적화 적용")}</button></div></section>
      <section><h3>{t("실시간 운영 알림")}</h3><strong className={`legacy-alert-badge level-${alertLevel}`}>{alertLevel}</strong><div className="legacy-operation-box"><p>{alertText}</p></div></section>
      <section><h3>{t("통합 잔고 요약")}</h3><div className="legacy-operation-box"><p>• {statisticsMode === "paper" ? t("가상") : t("체결 대조 완료")}{t(" 순손익: ")}{pnlLabel}<br />{t("• 계좌 잔고는 자산 통합에서 명시적으로 새로고침합니다.")}</p></div></section>
    </aside>
    <LogHelpDialog open={logHelpOpen} service={service} onClose={() => setLogHelpOpen(false)} onOpenManual={onOpenManual} />
  </section>;
}

export function LifeFinance({
  client,
  view = "personal_finance.service",
  assistantRequest = 0,
  initialQuestion = "",
  onOpenSettings,
}: {
  client: GatewayClient;
  view?: string;
  assistantRequest?: number;
  initialQuestion?: string;
  onOpenSettings?: () => void;
}) {
  const [data, setData] = useState<LifeFinanceSnapshot | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [innerTab, setInnerTab] = useState("대시보드");
  const [tx, setTx] = useState({ date: new Date().toISOString().slice(0, 10), amount: "", type: "지출", description: "", method: "카드" });
  const [goal, setGoal] = useState({ name: "", target_amount: "", deadline: "", priority: "중간" });
  const refresh = () => client.lifeFinance().then(setData).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "생활금융 조회 실패"));
  useEffect(() => { void refresh(); }, [client]);
  useEffect(() => {
    if (assistantRequest > 0) setInnerTab("AI 어시스턴트");
  }, [assistantRequest]);
  async function addTransaction() {
    try {
      await client.addLifeTransaction({ ...tx, amount: Number(tx.amount) });
      setTx({ ...tx, amount: "", description: "" }); setMessage("거래를 저장했습니다."); refresh();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "거래 저장 실패"); }
  }
  async function deleteTransaction(id: string) {
    if (!window.confirm("이 거래 기록을 삭제하시겠습니까?")) return;
    try { await client.deleteLifeTransaction(id); setMessage("거래를 삭제했습니다."); refresh(); } catch (reason) { setMessage(reason instanceof Error ? reason.message : "거래 삭제 실패"); }
  }
  async function addGoal() {
    try {
      await client.addLifeGoal({ ...goal, target_amount: Number(goal.target_amount), deadline: goal.deadline || null, category: "기타", description: "" });
      setGoal({ name: "", target_amount: "", deadline: "", priority: "중간" }); setMessage("재정 목표를 저장했습니다."); refresh();
    } catch (reason) { setMessage(reason instanceof Error ? reason.message : "목표 저장 실패"); }
  }
  async function deleteGoal(id: string) {
    if (!window.confirm("이 재정 목표를 삭제하시겠습니까?")) return;
    try { await client.deleteLifeGoal(id); setMessage("목표를 삭제했습니다."); refresh(); } catch (reason) { setMessage(reason instanceof Error ? reason.message : "목표 삭제 실패"); }
  }
  async function addGoalSavings(id: string) {
    const raw = window.prompt("저축 추가", "금액 (원):");
    if (raw === null) return;
    const amount = Number(raw.replaceAll(",", ""));
    if (!Number.isFinite(amount) || amount <= 0) { setMessage("올바른 저축 금액을 입력하세요."); return; }
    try { await client.addLifeGoalSavings(id, amount); setMessage("목표 저축액을 반영했습니다."); refresh(); }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : "저축 반영 실패"); }
  }
  const cumulative = (data?.summary.cumulative ?? {}) as Record<string, number>;
  const goals = data?.goals ?? [];
  const thisMonth = (data?.summary.this_month ?? {}) as Record<string, any>;
  const comparison = (data?.summary.comparison ?? {}) as Record<string, number>;
  const dashboardGoals = (data?.summary.goals?.top_goals ?? []) as Array<Record<string, any>>;
  const dashboardAlerts = (data?.summary.alerts ?? []) as Array<Record<string, any>>;
  const summaryPanel = <article className="panel finance-summary"><div className="panel-heading"><div><span className="eyebrow">PERSONAL FINANCE</span><h2>{view === "personal_finance.cashflow" ? "현금흐름 분석" : "생활금융 대시보드"}</h2></div><button className="secondary-button" type="button" onClick={refresh}>{t("새로고침")}</button></div>{error && <div className="inline-notice error-text">{error}</div>}{message && <div className="inline-notice">{message}</div>}<div className="metric-grid life-finance-kpi-grid"><div><span>{t("누적 수입")}</span><strong>{Number(cumulative.total_income ?? 0).toLocaleString()}{t("원")}</strong></div><div><span>{t("누적 지출")}</span><strong>{Number(cumulative.total_expenses ?? 0).toLocaleString()}{t("원")}</strong></div><div><span>{t("순자산 흐름")}</span><strong>{Number(cumulative.net_position ?? 0).toLocaleString()}{t("원")}</strong></div><div><span>{t("기록 거래")}</span><strong>{data?.transactions.length ?? 0}{t("건")}</strong></div></div></article>;
  const transactionPanel = <article className="panel finance-editor life-finance-entry-panel"><div className="panel-heading"><div><span className="eyebrow">TRANSACTIONS</span><h2>{t("거래")}</h2></div></div><div className="command-row life-finance-toolbar"><button type="button" className="primary-button" onClick={() => setTx({ ...tx, type: "지출" })}>{t("+ 지출 추가")}</button><button type="button" className="primary-button" onClick={() => setTx({ ...tx, type: "수입" })}>{t("+ 수입 추가")}</button><button type="button" className="secondary-button" onClick={refresh}>{t("새로고침")}</button></div><div className="form-grid life-finance-form"><label>{t("날짜")}<input type="date" value={tx.date} onChange={(event) => setTx({ ...tx, date: event.target.value })} /></label><label>{t("구분")}<select value={tx.type} onChange={(event) => setTx({ ...tx, type: event.target.value })}><option value={"지출"}>{t("지출")}</option><option value={"수입"}>{t("수입")}</option></select></label><label>{t("금액")}<input type="number" min="1" value={tx.amount} onChange={(event) => setTx({ ...tx, amount: event.target.value })} /></label><label>{t("결제 수단")}<input value={tx.method} onChange={(event) => setTx({ ...tx, method: event.target.value })} /></label></div><label className="life-finance-description">{t("설명")}<input value={tx.description} maxLength={500} onChange={(event) => setTx({ ...tx, description: event.target.value })} /></label><div className="command-row life-finance-save-row"><button className="primary-button" disabled={!tx.amount || !tx.description.trim()} onClick={addTransaction} type="button">{t("저장")}</button></div><div className="compact-list life-finance-records">{data?.transactions.slice(0, 30).map((item) => <div key={String(item.id)}><span>{String(item.date)} · {String(item.type)}</span><strong>{Number(item.amount ?? 0).toLocaleString()}{t("원")}</strong><small>{String(item.description ?? "")}</small><button className="text-button danger-text" onClick={() => deleteTransaction(String(item.id))} type="button">{t("삭제")}</button></div>)}{!data?.transactions.length && <div className="empty-state">{t("거래 내역이 없습니다.")}</div>}</div></article>;
  const goalPanel = <article className="panel goal-panel life-finance-entry-panel"><div className="panel-heading"><div><span className="eyebrow">GOALS</span><h2>{view === "personal_finance.goals" ? "생활금융 목표" : "목표"}</h2></div><span className="count-badge">{goals.length}{t("개")}</span></div><div className="form-grid life-finance-form"><label>{t("목표명")}<input value={goal.name} onChange={(event) => setGoal({ ...goal, name: event.target.value })} /></label><label>{t("목표 금액")}<input type="number" min="1" value={goal.target_amount} onChange={(event) => setGoal({ ...goal, target_amount: event.target.value })} /></label><label>{t("마감 기한")}<input type="date" value={goal.deadline} onChange={(event) => setGoal({ ...goal, deadline: event.target.value })} /></label><label>{t("우선순위")}<select value={goal.priority} onChange={(event) => setGoal({ ...goal, priority: event.target.value })}><option value={"높음"}>{t("높음")}</option><option value={"중간"}>{t("중간")}</option><option value={"낮음"}>{t("낮음")}</option></select></label></div><div className="command-row life-finance-save-row"><button className="secondary-button" disabled={!goal.name.trim() || !goal.target_amount} onClick={addGoal} type="button">{t("+ 목표 추가")}</button></div><div className="goal-list life-finance-records">{goals.map((goalItem) => <div key={String(goalItem.id)}><div><strong>{String(goalItem.name)}</strong><span>{Number(goalItem.progress_rate ?? 0).toFixed(1)}%</span></div><progress max={100} value={Number(goalItem.progress_rate ?? 0)} /><small>{Number(goalItem.current_amount ?? 0).toLocaleString()} / {Number(goalItem.target_amount ?? 0).toLocaleString()}{t("원")}</small><div className="command-row"><button className="text-button" onClick={() => addGoalSavings(String(goalItem.id))} type="button">{t("+ 저축")}</button><button className="text-button danger-text" onClick={() => deleteGoal(String(goalItem.id))} type="button">{t("삭제")}</button></div></div>)}{!goals.length && <div className="empty-state">{t("활성 목표가 없습니다. 새로운 목표를 추가해보세요.")}</div>}</div></article>;
  const dashboardPanel = <section className="life-dashboard-stack">
    <article className="panel legacy-life-monthly">
      <div className="panel-heading"><div><h2>{String(thisMonth.date_str ?? "이번 달")}{t(" 월간 재무 요약")}</h2></div><button className="secondary-button" type="button" onClick={refresh}>{t("새로고침")}</button></div>
      {error && <div className="inline-notice error-text">{error}</div>}{message && <div className="inline-notice">{message}</div>}
      <div className="legacy-life-metrics">
        <div><span>{t("수입")}</span><strong>{Number(thisMonth.total_income ?? 0).toLocaleString()}{t("원")}</strong></div>
        <div><span>{t("지출")}</span><strong>{Number(thisMonth.total_expense ?? 0).toLocaleString()}{t("원")}</strong></div>
        <div><span>{t("저축")}</span><strong>{Number(thisMonth.net_savings ?? 0).toLocaleString()}{t("원")}</strong></div>
        <div><span>{t("저축률")}</span><strong>{Number(thisMonth.savings_rate ?? 0).toFixed(1)}%</strong></div>
        <div><span>{t("누적 수입")}</span><strong>{Number(cumulative.total_income ?? 0).toLocaleString()}{t("원")}</strong></div>
        <div><span>{t("순 자산")}</span><strong>{Number(cumulative.net_position ?? 0).toLocaleString()}{t("원")}</strong></div>
      </div>
    </article>
    <article className="panel legacy-life-comparison">
      <div className="panel-heading"><div><h2>{t("이전 달과 비교")}</h2></div></div>
      <div className="legacy-life-comparison-grid">
        <div><span>{t("수입 변화")}</span><strong className={Number(comparison.income_change ?? 0) < 0 ? "negative" : "positive"}>{Number(comparison.income_change ?? 0) >= 0 ? "+" : ""}{Number(comparison.income_change ?? 0).toLocaleString()}{t("원")}</strong><small>{t("지난달 대비 수입")}</small></div>
        <div><span>{t("지출 변화")}</span><strong className={Number(comparison.expense_change ?? 0) > 0 ? "negative" : "positive"}>{Number(comparison.expense_change ?? 0) >= 0 ? "+" : ""}{Number(comparison.expense_change ?? 0).toLocaleString()}{t("원")}</strong><small>{t("지난달 대비 지출")}</small></div>
        <div><span>{t("저축 변화")}</span><strong className={Number(comparison.savings_change ?? 0) < 0 ? "negative" : "positive"}>{Number(comparison.savings_change ?? 0) >= 0 ? "+" : ""}{Number(comparison.savings_change ?? 0).toLocaleString()}{t("원")}</strong><small>{t("지난달 대비 순저축")}</small></div>
      </div>
    </article>
    {dashboardGoals.length > 0 && <article className="panel"><div className="panel-heading"><div><h2>{t("목표 진행 (")}{Number(data?.summary.goals?.active_count ?? dashboardGoals.length)}{t("개 진행 중)")}</h2></div></div><div className="goal-list">{dashboardGoals.map((goalItem) => <div key={String(goalItem.id)}><div><strong>{String(goalItem.name)}</strong><span>{Number(goalItem.progress_rate ?? 0).toFixed(1)}%</span></div><progress max={100} value={Number(goalItem.progress_rate ?? 0)} /><small>{Number(goalItem.current_amount ?? 0).toLocaleString()}{t("원 / ")}{Number(goalItem.target_amount ?? 0).toLocaleString()}{t("원 · 남은 금액 ")}{Number(goalItem.remaining_amount ?? 0).toLocaleString()}{t("원")}</small></div>)}</div></article>}
    {dashboardAlerts.length > 0 && <article className="panel"><div className="panel-heading"><div><h2>{t("금융 알림")}</h2></div></div><div className="alert-list">{dashboardAlerts.slice(0, 5).map((alert, index) => <section className={`alert-card ${String(alert.level ?? "info")}`} key={`${String(alert.title)}-${index}`}><strong>{String(alert.title ?? "알림")}</strong><p>{String(alert.message ?? "")}</p><small>{String(alert.action_hint ?? "")}</small></section>)}</div></article>}
  </section>;

  if (view === "personal_finance.cashflow") return <section className="finance-grid finance-detail-view">{summaryPanel}{transactionPanel}</section>;
  if (view === "personal_finance.goals") return <section className="finance-grid finance-detail-view">{summaryPanel}{goalPanel}</section>;

  const tabs = ["대시보드", "거래", "목표", "분석", "차트", "금융상품", "AI 어시스턴트"];
  return <section className="life-finance-service">
    <article className="panel life-finance-header"><h1>{t("생활금융 관리")}</h1><div className="command-row"><button type="button" onClick={() => setInnerTab("대시보드")}>{t("대시보드")}</button><button type="button" onClick={() => { setInnerTab("거래"); setTx({ ...tx, type: "지출" }); }}>{t("지출 추가")}</button><button type="button" onClick={() => { setInnerTab("거래"); setTx({ ...tx, type: "수입" }); }}>{t("수입 추가")}</button><button type="button" onClick={() => setInnerTab("목표")}>{t("목표 관리")}</button><button type="button" onClick={() => setInnerTab("금융상품")}>{t("금융상품")}</button></div></article>
    <nav className="life-finance-inner-tabs" aria-label={t("생활금융 서비스 내부 기능")}>{tabs.map((tab) => <button className={tab === innerTab ? "active" : ""} key={tab} type="button" onClick={() => setInnerTab(tab)}>{tab}</button>)}</nav>
    {innerTab === "대시보드" && dashboardPanel}
    {innerTab === "거래" && <section className="finance-grid single-column">{transactionPanel}</section>}
    {innerTab === "목표" && <section className="finance-grid single-column">{goalPanel}</section>}
    {innerTab === "분석" && <LifeFinanceAdvanced client={client} featureId="personal_finance.analysis" />}
    {innerTab === "차트" && <LifeFinanceAdvanced client={client} featureId="personal_finance.chart" />}
    {innerTab === "금융상품" && <LifeFinanceAdvanced client={client} featureId="personal_finance.products" />}
    {innerTab === "AI 어시스턴트" && <AssistantWorkspace client={client} service="personal_finance" initialQuestion={initialQuestion} onOpenSettings={onOpenSettings} onChartAnalysis={() => setInnerTab("차트")} />}
  </section>;
}
