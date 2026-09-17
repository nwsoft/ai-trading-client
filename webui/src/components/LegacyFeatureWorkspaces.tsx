import { useEffect, useMemo, useRef, useState } from "react";

import type { GatewayClient } from "../api";
import { sourcesForService, STOCK_SOURCES } from "../venueSources";
import { accountConnectionFailure, accountConnectionView } from "../accountConnection";
import type { RuntimeSnapshot, WorkspaceSnapshot } from "../types";
import { LogHelpDialog } from "./LogHelpDialog";
import { SourceTradeHistory } from "./SourceTradeHistory";
import { startSequentialPoll } from "../sequentialPoll";

function numberText(value: unknown, digits = 1) {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: digits }) : "—";
}

function metricText(value: unknown, digits = 1, suffix = "") {
  if (value === undefined || value === null || value === "") return "—";
  return `${numberText(value, digits)}${suffix}`;
}

function currencyMapText(values: Record<string, number> | undefined, digits = 4) {
  const entries = Object.entries(values ?? {}).filter(([, value]) => Number.isFinite(Number(value)));
  return entries.length
    ? entries.map(([currency, value]) => `${Number(value) > 0 ? "+" : ""}${numberText(value, currency === "KRW" ? 0 : digits)} ${currency}`).join(" · ")
    : "계산 전";
}

function executionCountLabel(count: number, status: string | undefined) {
  if (status === "unsupported") return "확인 불가";
  if (status === "not_checked") return "확인 전";
  if (status === "stored_only") return `${count}건 (저장 원장)`;
  if (status === "partial") return `${count}건 (저장 범위)`;
  return `${count}건`;
}

function spotHoldingClass(row: Record<string, any>) {
  const group = String(row.display_group ?? "market_unknown");
  if (group === "noahai_managed") {
    return {
      label: row.ownership === "mixed" ? "NoahAI 관리 + 외부" : "NoahAI 관리",
      className: "managed",
    };
  }
  if (group === "external_tradable") return { label: "수동/외부 · 자동 제외", className: "external" };
  if (group === "external_unsupported_market") return { label: "지원시장 외 · 자동 제외", className: "reference" };
  if (group === "reference_unavailable") return { label: "거래불가 · 자동 제외", className: "reference" };
  return { label: "시장 미확인 · 자동 제외", className: "reference" };
}

function sourceAccount(payload: Record<string, any> | null, source: string): Record<string, any> | null {
  if (!payload) return null;
  const sources = (payload.sources ?? payload.accounts ?? payload.snapshot?.sources ?? {}) as Record<string, any>;
  const account = sources[source] ?? sources[source.toLowerCase()] ?? payload[source];
  return account && typeof account === "object" ? account : null;
}

function normalizedBalanceRows(account: Record<string, any> | null, service: "blockchain" | "stock", source: string) {
  if (!account) return [] as Array<{ asset: string; value: unknown }>;
  // Runtime account snapshots keep the adapter's canonical response under
  // `balance`.  The previous Web UI inspected only the wrapper object, so a
  // successful response such as `{balance: {USDT: 25.9}}` was rendered as an
  // 비어 있는 일반 키 이름을 카드 값으로 노출하지 않습니다. Keep the same
  // source priority as the legacy dashboard's `_balance_metric_items`.
  const balanceEnvelope = account.balance;
  const raw = balanceEnvelope?.balance
    ?? balanceEnvelope?.balances
    ?? balanceEnvelope?.assets
    ?? balanceEnvelope?.wallet
    ?? balanceEnvelope
    ?? account.balances
    ?? account.assets
    ?? account.wallet
    ?? null;
  const rows: Array<{ asset: string; value: unknown }> = [];
  if (Array.isArray(raw)) {
    raw.forEach((item) => {
      if (!item || typeof item !== "object") return;
      rows.push({ asset: String(item.asset ?? item.currency ?? item.coin ?? item.symbol ?? "보유자산"), value: item.total ?? item.wallet_balance ?? item.walletBalance ?? item.balance ?? item.free ?? item.available_balance ?? item.available ?? item.value });
    });
  } else if (raw && typeof raw === "object") {
    Object.entries(raw).forEach(([asset, item]) => {
      rows.push({ asset, value: item && typeof item === "object" ? (item as Record<string, any>).total ?? (item as Record<string, any>).wallet_balance ?? (item as Record<string, any>).walletBalance ?? (item as Record<string, any>).balance ?? (item as Record<string, any>).free ?? (item as Record<string, any>).available_balance ?? (item as Record<string, any>).available : item });
    });
  }
  if (!rows.length && service === "blockchain") {
    const usdt = account.total_wallet_balance
      ?? account.wallet_balance
      ?? account.available_balance
      ?? balanceEnvelope?.total_wallet_balance
      ?? balanceEnvelope?.wallet_balance
      ?? balanceEnvelope?.available_balance;
    if (typeof usdt === "number" || typeof usdt === "string") rows.push({ asset: "USDT", value: usdt });
  }
  const quoteAsset = service === "stock" || ["upbit", "bithumb", "coinone"].includes(source.toLowerCase()) ? "KRW" : "USDT";
  const aliases: Record<string, string> = {
    TOTAL: "총 자산", TOTAL_BALANCE: "총 자산", TOTAL_ASSETS: "총 자산", EQUITY: "총 자산",
    AVAILABLE_BALANCE: "가용 잔고", AVAILABLE: "가용 잔고", FREE: "가용 잔고", CASH: "가용 잔고",
    UNREALIZED_PNL: "미실현 PnL", UNREALIZEDPNL: "미실현 PnL",
  };
  const normalized = rows
    .map((row) => ({ ...row, asset: aliases[row.asset.toUpperCase()] ?? row.asset.toUpperCase() }))
    .filter((row) => row.value !== undefined && row.value !== null && Number.isFinite(Number(row.value)));
  const priority = [quoteAsset, "총 자산", "가용 잔고", "미실현 PnL"];
  return normalized.sort((left, right) => {
    const leftIndex = priority.indexOf(left.asset);
    const rightIndex = priority.indexOf(right.asset);
    if (leftIndex >= 0 || rightIndex >= 0) return (leftIndex < 0 ? priority.length : leftIndex) - (rightIndex < 0 ? priority.length : rightIndex);
    return Number(right.value) - Number(left.value);
  });
}

function recordDate(row: Record<string, any>) {
  const raw = row.timestamp ?? row.created_at ?? row.time ?? row.at ?? row.exit_time ?? row.entry_time;
  const parsed = new Date(String(raw ?? ""));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function recordTime(row: Record<string, any>) {
  const parsed = recordDate(row);
  if (!parsed) return String(row.timestamp ?? row.created_at ?? row.time ?? row.at ?? "—").replace("T", " ").slice(0, 19);
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(parsed);
}

function periodRows(rows: Array<Record<string, any>>, period: string) {
  const now = new Date();
  if (period === "실시간") {
    const hourAgo = new Date(now.getTime() - 60 * 60 * 1000);
    return rows.filter((row) => {
      const at = recordDate(row);
      return at !== null && at >= hourAgo && at <= now;
    });
  }
  const kstToday = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
  const start = new Date(`${kstToday}T00:00:00+09:00`);
  if (period === "주간") start.setDate(start.getDate() - 6);
  if (period === "월간") start.setDate(1);
  return rows.filter((row) => {
    const at = recordDate(row);
    return at !== null && at >= start && at <= now;
  });
}

function recordSignal(row: Record<string, any>) {
  return String(row.signal ?? row.decision ?? row.action ?? "HOLD").toUpperCase();
}

export function LegacyAILearningWorkspace({ client, service, source, sources }: { client: GatewayClient; service: "blockchain" | "stock"; source: string; sources: string[] }) {
  const LEARNING_PAGE_SIZE = 50;
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const allowedSources = sourcesForService(service);
  const sourceOptions = sources.filter((item) => allowedSources.includes(item));
  const [selectedSource, setSelectedSource] = useState(sourceOptions.includes(source) ? source : sourceOptions[0] ?? "");

  function refresh() {
    if (!selectedSource) {
      setSnapshot(null);
      setError(`설정에서 사용할 ${service === "stock" ? "증권사" : "거래소"}를 선택하세요.`);
      setLoading(false);
      return;
    }
    setLoading(true);
    client.workspace(service, `${service}.ai_learning`, selectedSource, { offset: 0, limit: LEARNING_PAGE_SIZE })
      .then((next) => { setSnapshot(next); setError(""); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "AI 학습 데이터를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    const nextSource = sourceOptions.includes(source) ? source : sourceOptions[0] ?? "";
    setSelectedSource(nextSource);
  }, [service, source, sources.join("|")]);
  useEffect(() => { refresh(); }, [client, service, selectedSource]);

  async function loadMore() {
    if (!selectedSource || loading || !snapshot?.learning?.pagination?.has_more) return;
    const currentRows = (snapshot.learning.records ?? []) as Array<Record<string, any>>;
    setLoading(true);
    try {
      const older = await client.workspace(
        service,
        `${service}.ai_learning`,
        selectedSource,
        { offset: currentRows.length, limit: LEARNING_PAGE_SIZE },
      );
      const olderRows = (older.learning?.records ?? []) as Array<Record<string, any>>;
      setSnapshot({
        ...older,
        learning: {
          ...(older.learning ?? {}),
          records: [...olderRows, ...currentRows],
          summary: snapshot.learning.summary,
        },
      });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "이전 AI 학습 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  const rows = (snapshot?.learning?.records ?? []) as Array<Record<string, any>>;
  const summary = (snapshot?.learning?.summary ?? {}) as Record<string, any>;
  const fallbackSignals = rows.reduce((counts, row) => {
    const signal = recordSignal(row);
    if (signal in counts) counts[signal as keyof typeof counts] += 1;
    return counts;
  }, { LONG: 0, SHORT: 0, HOLD: 0 });
  const summaryComplete = summary.complete !== false;
  const signals = summaryComplete ? { ...fallbackSignals, ...(summary.signal_counts ?? {}) } : fallbackSignals;
  const confidenceValues = rows.map((row) => Number(row.confidence ?? row.score ?? 0)).filter(Number.isFinite);
  const averageConfidence = Number(summaryComplete && summary.average_confidence !== undefined ? summary.average_confidence : (confidenceValues.length ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length : 0));
  const totalCount = Number(summary.total_count ?? rows.length);
  const hasMore = Boolean(snapshot?.learning?.pagination?.has_more);
  const totalCountLabel = snapshot?.learning?.pagination?.total_count == null
    ? (hasMore ? `${rows.length}개 이상` : `${rows.length}`)
    : `${totalCount}`;
  const todayCount = summaryComplete ? Number(summary.today_count ?? 0) : periodRows(rows, "오늘").length;
  const weeklyCount = summaryComplete ? Number(summary.weekly_count ?? rows.length) : periodRows(rows, "주간").length;
  const latest = rows.at(-1);
  const summaryScope = summaryComplete ? (service === "stock" ? "선택 증권사 DB 분석 기록 기준" : "전체 운영 파일 기준") : `최근 ${rows.length}개 표시 기준`;

  return <section className="legacy-ai-learning">
    <header className="legacy-learning-summary"><div><b>오늘: {todayCount}개</b><b>주간: {weeklyCount}개</b><b>신호: LONG({signals.LONG}) SHORT({signals.SHORT}) HOLD({signals.HOLD})</b><small>{summaryScope}</small></div><strong className={error || snapshot?.learning?.status === "unavailable" ? "negative" : "positive"}>{error || snapshot?.learning?.status === "unavailable" ? "조회 실패" : rows.length ? "분석 기록 있음" : "분석 기록 대기"}</strong></header>
    {service === "stock" && <p className="workspace-copy">증권사별 분석 기록을 같은 DB에서 기관 식별자로 분리 조회합니다. 파일이 같아도 다른 증권사의 기록을 섞지 않습니다. 현재 국내 주식·국내 상장 ETF 분석이며, 미국 시장 시세 조회는 해외주식 자동매매·학습 지원을 의미하지 않습니다. 과거 기록에 없는 신호·지표는 추정하지 않습니다.</p>}
    <label className="legacy-learning-source">{service === "stock" ? "증권사" : "거래소"}: <select value={selectedSource} disabled={!sourceOptions.length} onChange={(event) => setSelectedSource(event.target.value)}>{!sourceOptions.length && <option value="">설정에서 선택 필요</option>}{sourceOptions.map((item) => <option value={item} key={item}>{item}</option>)}</select></label>
    <article className="legacy-learning-status"><h2>AI 학습 모니터 ({service === "stock" ? "주식/ETF" : "암호화폐"})</h2><div><span>현재 상태:</span><b>{latest ? `최근: ${String(latest.symbol ?? latest.coin ?? "전체")} ${recordSignal(latest)} (신뢰도 ${numberText(latest.confidence ?? latest.score, 2)})` : "대기 중"}</b></div><progress max={100} value={rows.length ? 100 : 0} /></article>
    <article className="legacy-learning-data"><header><div><h2>AI 학습 데이터</h2><small>최근 {rows.length}개 · 저장 근거: {String(snapshot?.learning?.source ?? "확인 중...")}</small></div><button type="button" disabled={loading} onClick={refresh}>새로고침</button></header><div className={`legacy-workspace-feedback${error ? " error-text" : ""}`} role="status" aria-live="polite">{error}</div><div className="legacy-learning-table"><div className="legacy-learning-row header"><span>시간</span><span>{service === "stock" ? "종목" : "코인"}</span><span>시그널</span><span>신뢰도</span><span>RSI</span><span>MACD</span><span>트렌드</span><span>추론</span></div><div className="legacy-learning-body">{[...rows].reverse().map((row, index) => <div className="legacy-learning-row" key={String(row.id ?? `${recordTime(row)}-${index}`)}><span>{recordTime(row).slice(11) || "—"}</span><b>{String(row.symbol ?? row.coin ?? row.ticker ?? "—")}</b><strong className={recordSignal(row) === "LONG" ? "positive" : recordSignal(row) === "SHORT" ? "negative" : "warning"}>{recordSignal(row)}</strong><span>{row.confidence == null && row.score == null ? '—' : numberText(row.confidence ?? row.score, 2)}</span><span>{row.rsi == null && row.RSI == null ? '—' : numberText(row.rsi ?? row.RSI, 4)}</span><span>{row.macd == null && row.MACD == null ? '—' : numberText(row.macd ?? row.MACD, 4)}</span><span>{String(row.trend ?? row.market_trend ?? '—')}</span><span title={String(row.reasoning ?? row.reason ?? row.inference ?? row.analysis ?? "")}>{String(row.reasoning ?? row.reason ?? row.inference ?? row.analysis ?? "—")}</span></div>)}{!loading && !rows.length && <div className="empty-state">저장된 AI 학습 데이터가 없습니다.</div>}{hasMore && <button className="legacy-learning-more" type="button" disabled={loading} onClick={() => void loadMore()}>{loading ? "불러오는 중…" : `이전 데이터 ${LEARNING_PAGE_SIZE}개 더보기`}</button>}</div></div></article>
    <article className="legacy-learning-stats"><h2>AI 학습 통계</h2><div><span>{service === "stock" ? "선택 증권사 분석 기록 수" : "운영 파일 학습 수"}: <b>{totalCountLabel}</b></span><span>평균 신뢰도: <b>{totalCount ? numberText(averageConfidence, 2) : "—"}</b></span><span>마지막 업데이트: <b>{latest ? recordTime(latest).slice(11) : "N/A"}</b></span><span>LONG 신호: <b>{signals.LONG}</b></span><span>SHORT 신호: <b>{signals.SHORT}</b></span><span>HOLD 신호: <b>{signals.HOLD}</b></span></div></article>
  </section>;
}

export function LegacyAIReportWorkspace({ client, service, source: _source, sources, onAskAssistant }: { client: GatewayClient; service: "blockchain" | "stock"; source: string; sources: string[]; onAskAssistant?: (question: string) => void }) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [activeTab, setActiveTab] = useState("오늘");
  const [reportSource, setReportSource] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState("");
  const [reportPage, setReportPage] = useState(0);
  const reportRequestSequence = useRef(0);
  const REPORT_PAGE_SIZE = 100;
  const allowedSources = sourcesForService(service);
  const sourceOptions = sources.filter((item) => allowedSources.includes(item));

  function refresh() {
    const requestSequence = ++reportRequestSequence.current;
    if (service === "stock" && !sourceOptions.length) {
      setSnapshot(null);
      setError("설정에서 사용할 증권사를 선택하세요.");
      setLoading(false);
      return;
    }
    setLoading(true);
    const requestedPeriod = activeTab === "주간" ? "week" : activeTab === "월간" ? "month" : activeTab === "실시간" ? "realtime" : "today";
    client.workspace(service, `${service}.ai_reports`, reportSource, {
      reportPeriod: requestedPeriod,
      reportOffset: reportPage * REPORT_PAGE_SIZE,
      reportLimit: REPORT_PAGE_SIZE,
    })
      .then((next) => {
        if (requestSequence !== reportRequestSequence.current) return;
        setSnapshot(next);
        setError("");
      })
      .catch((reason: unknown) => {
        if (requestSequence !== reportRequestSequence.current) return;
        setError(reason instanceof Error ? reason.message : "AI 리포트를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (requestSequence === reportRequestSequence.current) setLoading(false);
      });
  }
  useEffect(() => { setReportSource(""); }, [service]);
  useEffect(() => { setReportPage(0); }, [service, reportSource, activeTab]);
  useEffect(() => {
    if (reportSource && !sourceOptions.includes(reportSource)) setReportSource("");
    else refresh();
  }, [client, service, reportSource, activeTab, reportPage, sources.join("|")]);

  const qualityRows = snapshot?.execution_quality?.rows ?? [];
  const periodKey = activeTab === "주간" ? "week" : activeTab === "월간" ? "month" : activeTab === "실시간" ? "realtime" : "today";
  const periodMetric = snapshot?.report_periods?.periods?.[periodKey];
  const tradeRows = (periodMetric?.detail_rows ?? []) as Array<Record<string, any>>;
  const reportRows = activeTab === "실행 품질"
    ? qualityRows
    : tradeRows;
  const periodClosed = Number(periodMetric?.closed_count ?? 0);
  const periodReconciled = Number(periodMetric?.reconciled_closed_count ?? 0);
  const periodUnresolved = Number(periodMetric?.unresolved_closed_count ?? Math.max(0, periodClosed - periodReconciled));
  const periodWins = Number(periodMetric?.winning_count ?? 0);
  const periodWinRate = Number(periodMetric?.win_rate ?? 0);
  const realtimeLosses = Number(periodMetric?.losing_count ?? 0);
  const confirmedExecutions = Number(periodMetric?.execution_count ?? 0);
  const pnlText = currencyMapText(periodMetric?.pnl_by_currency);
  const feeText = currencyMapText(periodMetric?.fees_by_currency);
  // Keep the legacy report contract name while sourcing the value from the
  // exact per-currency SQL aggregate rather than a capped recent-row window.
  const realtimeFees = feeText;
  const executedNotionalText = currencyMapText(periodMetric?.execution_notional_by_currency);
  const realtimePrompt = periodReconciled
    ? `최근 1시간 NoahAI 청산 ${periodClosed}건 중 체결 대조 완료 ${periodReconciled}건을 분석해줘. 확정 승률 ${numberText(periodWinRate, 2)}%, 통화별 확정 순손익 ${pnlText}, 통화별 Fee ${realtimeFees}, 대조 미확정 ${periodUnresolved}건이다. 거래소 확인 체결은 ${confirmedExecutions}건이다. 장점, 단점, 주의사항, 구체적인 개선 방안을 구분하고 설정을 자동 변경하거나 주문하지 마.`
    : periodClosed
      ? `최근 1시간 NoahAI 청산 ${periodClosed}건이 있지만 체결 대조 완료는 0건이고 대조 미확정은 ${periodUnresolved}건이다. 승률이나 손익을 0으로 단정하지 말고 주문 ID·체결수량·수수료 통화 등 대조 근거 부족 원인을 설명해줘. 설정을 자동 변경하거나 주문하지 마.`
      : "최근 1시간 종료 거래가 없습니다. 거래가 없는 원인을 현재 실행 상태와 설정 기준으로 점검하되 설정을 자동 변경하거나 주문하지 마.";

  const periodTitle = activeTab === "실행 품질"
    ? "실행 품질 메트릭 (고급 매매 계층)"
    : activeTab === "오늘"
      ? "오늘 거래 요약"
      : activeTab === "주간"
        ? "주간 거래 요약"
        : activeTab === "월간"
          ? "월간 거래 요약"
          : "실시간 거래 분석 (최근 1시간)";
  const detailTitle = activeTab === "오늘"
    ? "상세 거래 내역"
    : activeTab === "주간"
      ? "주간 상세 분석"
      : activeTab === "월간"
        ? "월간 상세 분석"
        : activeTab === "실시간"
          ? "현재 거래 상황 분석"
          : "최근 트레이딩 사이클";
  const reportMetrics = [
    { label: "거래소 확인 체결", value: executionCountLabel(confirmedExecutions, periodMetric?.execution_history_status ?? snapshot?.report_periods?.execution_history_status), tone: "blue" },
    { label: "청산 완료", value: `${periodClosed}건`, tone: "cyan" },
    { label: "체결 대조 완료 승률", value: periodReconciled ? `${numberText(periodWinRate, 1)}%` : "계산 전", tone: "green" },
    { label: "통화별 확정 순손익", value: periodReconciled ? pnlText : "계산 전", tone: "purple" },
  ];

  function runRealtimeAnalysis() {
    setActiveTab("실시간");
  }

  async function sendCurrentReport() {
    setLoading(true);
    setNotificationMessage("연동 채널로 리포트 요약을 보내는 중입니다…");
    const selectedLabel = reportSource ? reportSource.toUpperCase() : "전체";
    const message = [
      `기간: ${activeTab} · 대상: ${selectedLabel}`,
      `거래소 확인 체결: ${confirmedExecutions}건`,
      `NoahAI 청산 완료: ${periodClosed}건`,
      `체결 대조: 완료 ${periodReconciled}건 · 미확정 ${periodUnresolved}건`,
      `확정 승률: ${periodReconciled ? `${numberText(periodWinRate, 2)}%` : "계산 전"}`,
      `통화별 확정 순손익: ${periodReconciled ? pnlText : "계산 전"}`,
      `통화별 수수료: ${periodClosed ? feeText : "계산 전"}`,
      `원장 연결: ${Number(periodMetric?.linked_closed_count ?? 0)}건 · 미연결 ${Number(periodMetric?.unlinked_closed_count ?? 0)}건`,
      "KRW와 USDT는 환율 정책 없이 합산하지 않습니다.",
    ].join("\n");
    try {
      await client.sendReportNotification(`${activeTab} AI 거래 리포트`, message, reportSource || service);
      setNotificationMessage("리포트 요약을 활성화된 Discord·Telegram 채널의 발송 큐에 넣었습니다.");
    } catch (reason) {
      setNotificationMessage(reason instanceof Error ? reason.message : "리포트 요약을 보내지 못했습니다.");
    } finally { setLoading(false); }
  }

  return <section className="legacy-ai-report">
    <header><h1>AI 자동 리포트</h1><p>AI가 실제 거래 데이터를 분석하여 생성하는 리포트입니다.</p></header>
    <nav className="report-period-tabs">{["오늘", "주간", "월간", "실시간", "실행 품질"].map((tab, index) => <button className={activeTab === tab ? "active" : ""} type="button" key={tab} onClick={() => { setReportPage(0); setActiveTab(tab); }}><span aria-hidden="true">{["●", "◐", "◒", "◆", "✓"][index]}</span>{tab}</button>)}</nav>
    {activeTab === "실시간" ? <div className="legacy-report-tab-body realtime">
      <article className="legacy-report-summary-card"><h2>실시간 거래 분석 (최근 1시간)</h2>{error && <div className="inline-notice error-text">{error}</div>}<div className="legacy-report-summary">{periodClosed ? <><p><b>분석 시간:</b> {recordTime({ timestamp: new Date().toISOString() })}</p><p><b>청산 완료:</b> {periodClosed}건 · <b>체결 대조:</b> {periodReconciled}건 · <b>미확정:</b> {periodUnresolved}건</p><p><b>확정 승률:</b> {periodReconciled ? `${numberText(periodWinRate, 2)}%` : "계산 전"}</p><p><b>통화별 확정 순손익:</b> {periodReconciled ? pnlText : "계산 전"} · <b>통화별 Fee:</b> {realtimeFees}</p><p>환율 정책 없이 KRW·USDT는 합산하지 않습니다.</p></> : <><p>최근 1시간 청산 완료 거래가 없습니다.</p><p>거래소 확인 체결 {confirmedExecutions}건과 포지션 청산은 서로 다른 단위입니다.</p><p>시장 상황과 실행 상태를 계속 모니터링하세요.</p></>}</div></article>
      <article className="legacy-report-detail-card realtime-analysis"><h2>현재 거래 상황 분석</h2><div className="legacy-report-summary">{periodClosed ? <><p><b>확정 수익:</b> {periodWins}건 · <b>확정 손실:</b> {realtimeLosses}건</p><p><b>대조 상태:</b> 완료 {periodReconciled}건 · 미확정 {periodUnresolved}건입니다.</p><p><b>원장 연결:</b> 청산 {periodClosed}건 중 거래소 체결과 연결 {Number(periodMetric?.linked_closed_count ?? 0)}건, 미연결 {Number(periodMetric?.unlinked_closed_count ?? 0)}건입니다.</p><p><b>주의사항:</b> 부분체결·진입·청산 때문에 체결 건수와 청산 건수는 1:1이 아닙니다.</p></> : <p>분석할 청산 거래 데이터가 없습니다.</p>}</div></article>
      <article className="legacy-report-detail-card realtime-transfer"><h2>AI 어시스턴트 연동</h2><p>{periodClosed ? "통화별 실시간 성과와 원장 연결 상태를 전달합니다. 자동 적용이나 주문은 실행하지 않습니다." : "현재 청산 데이터가 없어 원인 점검 요청만 전달합니다."}</p><button type="button" onClick={() => onAskAssistant?.(realtimePrompt)}>AI 어시스턴트에 전달</button></article>
    </div> : <div className="legacy-report-tab-body">
      <article className={`legacy-report-summary-card ${activeTab === "실행 품질" ? "quality" : ""}`}><div className="legacy-report-card-title"><div><span className="report-eyebrow">근거 기반 요약</span><h2>{periodTitle}</h2></div>{activeTab === "실행 품질" && <button type="button" onClick={refresh} disabled={loading}>{loading ? "갱신 중…" : "메트릭 갱신"}</button>}</div>{error && <div className="inline-notice error-text">{error}</div>}{activeTab !== "실행 품질" ? <div className="legacy-report-summary professional"><div className="report-summary-metrics">{reportMetrics.map((metric) => <div className={`tone-${metric.tone}`} key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong></div>)}</div><div className="report-summary-copy"><section><b>거래 상태</b><p>{snapshot?.report_periods?.execution_history_available === false ? "이 증권/거래소의 외부 체결 이력은 아직 공통 원장으로 확인할 수 없습니다." : confirmedExecutions ? `선택 기간의 거래소 확인 체결 ${confirmedExecutions}건입니다.` : "선택 기간에 거래소가 확인한 체결이 없습니다."}</p></section><section><b>성과 계산</b><p>{periodClosed ? `NoahAI 청산 완료 ${periodClosed}건 중 수익 거래 ${periodWins}건입니다.` : confirmedExecutions ? "체결은 있으나 청산 완료 포지션이 없어 승률과 손익은 계산하지 않습니다." : "청산 완료 표본이 없어 승률과 손익을 계산하지 않습니다."}</p></section><section><b>체결 규모</b><p>{executedNotionalText} · 통화가 다른 금액은 임의 합산하지 않습니다.</p></section><section><b>원장 연결</b><p>청산 {periodClosed}건 중 체결 연결 {Number(periodMetric?.linked_closed_count ?? 0)}건 · 미연결 {Number(periodMetric?.unlinked_closed_count ?? 0)}건 · 레거시 출처 미확정 {Number(periodMetric?.legacy_unknown_count ?? 0)}건</p></section><section><b>정산 대조</b><p>{periodMetric?.ledger_reconciled === false ? "요약과 상세 원장 체크섬이 일치하지 않습니다. 이 리포트를 확정 정산으로 사용하지 마세요." : `기간 상세 원장 ${Number(periodMetric?.detail_total_count ?? periodClosed)}건과 통화별 손익·수수료를 대조했습니다.`}</p></section><section><b>다음 확인</b><p>{periodMetric?.ledger_reconciled === false ? "거래소 필터·기간·원장 손상 여부를 확인하고 새로고침하세요." : "상세 거래의 청산 사유와 체결 연결 상태를 확인하세요."}</p></section></div></div> : <div className="legacy-report-summary quality-copy"><section><b>표시 범위</b><p>최근 사이클의 quality_score, 슬리피지, 지연과 이상 감지 결과를 표시합니다.</p></section><section><b>안전 경계</b><p>메트릭 갱신은 저장된 실행 기록만 다시 조회하며 주문이나 설정 변경을 실행하지 않습니다.</p></section></div>}</article>
      <article className="legacy-report-detail-card"><h2>{detailTitle}</h2><div className="legacy-report-list">{reportRows.map((row, index) => { const closedTrade = activeTab !== "실행 품질" && row.pnl !== undefined && row.exit_time; return <article key={String(row.id ?? `${activeTab}-${index}`)}><header><b>{activeTab === "실행 품질" ? `${String(row.source || reportSource || "전체").toUpperCase()} · ${String(row.engine ?? "실행 엔진")}` : `${String(row.exchange || reportSource || "전체").toUpperCase()} · ${String(row.symbol ?? row.coin ?? row.event ?? "전체")}`}</b><span>{recordTime(row)}</span></header><p>{activeTab === "실행 품질" ? String(row.daily_briefing ?? row.message ?? (Array.isArray(row.anomalies) && row.anomalies.length ? `이상 감지: ${row.anomalies.join(", ")}` : "최근 사이클 실행 품질을 확인했습니다.")) : closedTrade ? `${String(row.side || "포지션").toUpperCase()} 청산 · 실현손익 ${Number(row.pnl) > 0 ? "+" : ""}${numberText(row.pnl, String(row.currency) === "KRW" ? 0 : 6)} ${String(row.currency || "")} (${Number(row.pnl_percent) > 0 ? "+" : ""}${numberText(row.pnl_percent, 3)}%) · 수수료 ${numberText(row.fees, String(row.currency) === "KRW" ? 0 : 6)} ${String(row.currency || "")} · 진입가 ${numberText(row.entry_price, 8)}${row.exit_price !== undefined ? ` → 청산가 ${numberText(row.exit_price, 8)}` : ""}` : String(row.summary ?? row.reason ?? row.analysis ?? row.details ?? row.status ?? "저장된 상세 설명이 없습니다.")}</p>{activeTab === "실행 품질" && <dl className="quality-metric-grid"><div><dt>품질 점수</dt><dd>{metricText(row.quality_score, 2)}</dd></div><div><dt>주문 시도</dt><dd>{metricText(row.attempted_orders ?? row.order_count, 0, "건")}</dd></div><div><dt>실패</dt><dd>{metricText(row.failed_orders ?? (row.success === false ? 1 : row.success === true ? 0 : undefined), 0, "건")}</dd></div><div><dt>평균 지연</dt><dd>{metricText(row.avg_latency_ms ?? row.latency_ms ?? row.latency, 2, "ms")}</dd></div><div><dt>슬리피지</dt><dd>{metricText(row.avg_slippage_bps ?? row.slippage_bps ?? row.slippage ?? row.slippage_pct, 2, "bps")}</dd></div><div><dt>상태</dt><dd>{Array.isArray(row.anomalies) && row.anomalies.length ? `주의 ${row.anomalies.length}건` : String(row.status ?? row.result ?? "정상")}</dd></div></dl>}</article>; })}{!loading && !reportRows.length && <div className="empty-state report-empty">{activeTab === "실행 품질" ? (snapshot?.execution_quality?.message ?? "최근 사이클 실행 품질 기록이 없습니다.") : periodClosed ? `요약에는 청산 ${periodClosed}건이 있으나 상세 원장 행을 불러오지 못했습니다. 새로고침 후에도 같으면 데이터 원장을 점검하세요.` : confirmedExecutions ? "거래소 확인 체결은 있지만 아직 청산 완료된 NoahAI 포지션이 없습니다." : "선택 기간에 청산 완료된 NoahAI 거래가 없습니다."}</div>}</div>{activeTab !== "실행 품질" && Number(periodMetric?.detail_total_count ?? 0) > REPORT_PAGE_SIZE && <div className="legacy-report-pagination"><button type="button" disabled={loading || reportPage === 0} onClick={() => setReportPage((page) => Math.max(0, page - 1))}>이전 {REPORT_PAGE_SIZE}건</button><span>{Number(periodMetric?.detail_offset ?? 0) + 1}–{Number(periodMetric?.detail_offset ?? 0) + reportRows.length} / {Number(periodMetric?.detail_total_count ?? 0)}건</span><button type="button" disabled={loading || !periodMetric?.detail_has_more} onClick={() => setReportPage((page) => page + 1)}>다음 {REPORT_PAGE_SIZE}건</button></div>}</article>
    </div>}
    <div className="report-notification-status" role="status" aria-live="polite">{notificationMessage}</div>
    <footer><label>{service === "stock" ? "증권사" : "거래소"}: <select value={reportSource} onChange={(event) => setReportSource(event.target.value)}><option value="">전체</option>{sourceOptions.map((item) => <option value={item} key={item}>{item}</option>)}</select></label><button type="button" onClick={refresh} disabled={loading}>전체 새로고침</button><button type="button" onClick={() => void sendCurrentReport()} disabled={loading}>연동 채널로 보내기</button><button className="legacy-realtime-report-button" type="button" onClick={runRealtimeAnalysis} disabled={loading}>실시간 분석</button></footer>
  </section>;
}

export function MarketTrendWorkspace({ client, service, source }: { client: GatewayClient; service: "blockchain" | "stock"; source: string }) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [marketRows, setMarketRows] = useState<Array<{ symbol: string; name?: string; price?: number; change: number; volumeChange: number; direction: string; source?: string; tradedAt?: string; marketStatus?: string }>>([]);
  const [stockIndices, setStockIndices] = useState<Array<Record<string, any>>>([]);
  const [sentiment, setSentiment] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  function refresh() {
    setLoading(true);
    const symbols = service === "stock" ? ["005930", "000660", "035420", "035720", "005380", "373220"] : ["BTCUSDT", "ETHUSDT", "BNBUSDT"];
    const marketRequest = service === "stock"
      ? client.stockOverview(symbols)
      : Promise.all(symbols.map((symbol) => client.candles(symbol, "1d", 30, source || "binance", "futures").catch(() => null)));
    Promise.all([
      client.workspace(service, `${service}.trends`, source),
      marketRequest,
      service === "blockchain" && (!source || source === "binance") ? client.marketSentiment("BTCUSDT").catch(() => null) : Promise.resolve(null),
    ]).then(([next, marketPayload, nextSentiment]) => {
      setSnapshot(next as WorkspaceSnapshot);
      setSentiment(nextSentiment as Record<string, any> | null);
      if (service === "stock") {
        const publicSnapshot = marketPayload as Record<string, any>;
        const quotes = Array.isArray(publicSnapshot.quotes) ? publicSnapshot.quotes : [];
        setStockIndices(Array.isArray(publicSnapshot.indices) ? publicSnapshot.indices : []);
        setMarketRows(quotes.filter((row) => row?.status === "ok").map((row) => {
          const change = Number(row.change ?? 0);
          return { symbol: String(row.symbol), name: String(row.name ?? row.symbol), price: Number(row.price ?? 0), change, volumeChange: row.volume == null ? Number.NaN : Number(row.volume), direction: change > .25 ? "상승" : change < -.25 ? "하락" : "중립", source: String(row.source ?? publicSnapshot.source ?? "naver_finance_public"), tradedAt: String(row.traded_at ?? ""), marketStatus: String(row.market_status ?? "") };
        }));
      } else {
        setStockIndices([]);
        const candles = marketPayload as Array<any>;
        setMarketRows(candles.flatMap((payload, index) => {
        const points = payload?.candles ?? [];
        if (points.length < 2) return [];
        const current = Number(points.at(-1)?.close ?? 0);
        const previous = Number(points.at(-7)?.close ?? points[0]?.close ?? current);
        const currentVolume = Number(points.at(-1)?.volume ?? 0);
        const previousVolume = Number(points.at(-7)?.volume ?? points[0]?.volume ?? currentVolume);
        const change = previous ? (current - previous) / previous * 100 : 0;
        const volumeChange = previousVolume ? (currentVolume - previousVolume) / previousVolume * 100 : 0;
          return [{ symbol: symbols[index], change, volumeChange, direction: change > .25 ? "상승" : change < -.25 ? "하락" : "중립", source: String(payload?.source ?? source) }];
        }));
      }
      setError("");
    }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "시장 트렌드를 불러오지 못했습니다."))
      .finally(() => setLoading(false));
  }
  useEffect(() => {
    refresh();
  }, [client, service, source]);
  const candidates = snapshot?.selected_coins ?? [];
  const stats = snapshot?.statistics ?? [];
  const trading = snapshot?.trading;
  const closed = Number(trading?.closed_count ?? 0);
  const pnl = Number(trading?.pnl_by_currency?.[service === "stock" ? "KRW" : "USDT"] ?? 0);
  const sampleCount = service === "stock" ? stats.length : candidates.length;
  const topCandidates = candidates.slice(0, 5).map((row) => String(row.symbol ?? row.coin ?? "")).filter(Boolean);
  const averageChange = marketRows.length ? marketRows.reduce((sum, row) => sum + row.change, 0) / marketRows.length : 0;
  const direction = marketRows.length ? averageChange > .25 ? "상승" : averageChange < -.25 ? "하락" : "중립" : "연결 중";
  const fundingRate = sentiment == null ? null : Number(sentiment.funding_rate ?? 0);
  const longShortRatio = sentiment == null ? null : Number(sentiment.long_short_ratio ?? 1);
  const fearGreed = longShortRatio == null ? "연결 중" : longShortRatio > 1.2 ? "탐욕" : longShortRatio < .8 ? "공포" : "중립";
  const positiveBreadth = marketRows.filter((row) => row.change > 0).length;
  const status = marketRows.length ? service === "stock" ? `공개 시세 ${marketRows.length}개${marketRows[0]?.tradedAt ? ` · 기준 ${marketRows[0].tradedAt.replace("T", " ")}` : ""}` : `실시간 표본 ${marketRows.length}개` : sampleCount > 0 ? `저장 표본 ${sampleCount}건` : "수집 대기";
  const indexText = stockIndices.filter((row) => row?.status === "ok").map((row) => `${String(row.name ?? row.symbol)} ${Number(row.change ?? 0) >= 0 ? "+" : ""}${Number(row.change ?? 0).toFixed(2)}%`).join(" · ");
  const stockSectors = [["IT·반도체", ["005930", "000660"]], ["인터넷·플랫폼", ["035420", "035720"]], ["자동차", ["005380"]], ["2차전지", ["373220"]]] as Array<[string, string[]]>;
  const sectorText = stockSectors.map(([name, symbols]) => {
    const rows = marketRows.filter((row) => symbols.includes(row.symbol));
    const change = rows.length ? rows.reduce((sum, row) => sum + row.change, 0) / rows.length : null;
    return `• ${name}: ${change == null ? "데이터 없음" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}`;
  }).join("\n");
  return <section className="legacy-market-trend">
    <header className="legacy-market-trend-title"><span>시장 트렌드 인사이트</span><button type="button" onClick={refresh} disabled={loading}>{loading ? "수집 중…" : "새로고침"}</button></header>
    <div className="legacy-trend-chips">
      <span>시장 방향: {direction} {marketRows.length ? `${averageChange >= 0 ? "+" : ""}${averageChange.toFixed(2)}%` : ""}</span>
      <span>{service === "stock" ? "섹터 브레드스" : "펀딩비"}: {service === "stock" ? marketRows.length ? `${positiveBreadth}/${marketRows.length} 섹터 상승` : "연동 대기" : fundingRate == null ? "연결 중" : fundingRate.toFixed(4)}</span>
      <span>{service === "stock" ? "KOSPI/KOSDAQ" : "공포/탐욕"}: {service === "stock" ? indexText || "연결 중" : fearGreed}</span>
    </div>
    <div className={`legacy-workspace-feedback${error ? " error-text" : ""}`} role="status" aria-live="polite">{error}</div>
    <div className="legacy-trend-grid">
      <article><h3>{service === "stock" ? "주식 시장 방향 · 모멘텀" : "시장 방향 · 모멘텀"}</h3><div className="legacy-trend-content"><p>{marketRows.length ? marketRows.map((row) => `• ${row.name ?? row.symbol}(${row.symbol}): ${row.direction} ${row.change >= 0 ? "+" : ""}${row.change.toFixed(2)}%`).join("\n") : `• ${status}\n• 공개 시세가 확보되면 방향성을 표시합니다.`}</p></div></article>
      <article><h3>{service === "stock" ? "업종 · 섹터 흐름" : "대표 코인 · 섹터 흐름"}</h3><div className="legacy-trend-content"><p>{service === "stock" ? marketRows.length ? sectorText : "• 네이버 금융 공개 시세 연결 후 업종 흐름을 표시합니다." : topCandidates.length ? `• 저장 후보: ${topCandidates.join(", ")}\n• 대표 코인 평균 변화: ${averageChange >= 0 ? "+" : ""}${averageChange.toFixed(2)}%` : marketRows.map((row) => `• ${row.symbol}: ${row.change.toFixed(2)}%`).join("\n") || "• 저장된 대표 코인 후보가 없습니다."}</p></div></article>
      <article><h3>{service === "stock" ? "투자 심리 · 거래량" : "시장 심리 · 거래량 지표"}</h3><div className="legacy-trend-content"><p>{marketRows.length ? marketRows.map((row) => `• ${row.name ?? row.symbol}: ${service === "stock" ? `거래량 ${Number.isFinite(row.volumeChange) ? row.volumeChange.toLocaleString() : "미제공"}` : `거래량 ${row.volumeChange >= 0 ? "+" : ""}${row.volumeChange.toFixed(1)}%`}`).join("\n") : "• 확인 가능한 거래량 표본이 없습니다."}<br />• 출처: {service === "stock" ? "네이버 금융 공개 시세(계좌·주문과 분리)" : "선택 거래소 공개 시세"}<br />• 현재 상태: {status}</p></div></article>
      <article><h3>{service === "stock" ? "내 포트폴리오 트렌드" : "나의 포트폴리오 트렌드"}</h3><div className="legacy-trend-content"><p>• 저장된 종료 거래: {closed}건<br />• 실현손익: {numberText(pnl, service === "stock" ? 0 : 4)} {service === "stock" ? "KRW" : "USDT"}<br />• 잔고·미실현손익은 계좌 새로고침 결과와 분리합니다.</p></div></article>
      <article className="legacy-trend-ai"><h3>AI 전략 상태</h3><div className="legacy-trend-content"><p>• 현재 저장 표본과 실행 결과를 분리해 표시합니다.<br />• 표본이 없거나 기준을 충족하지 못하면 HOLD를 유지합니다.<br />• 전략 변경·승인·PAPER 상태는 전략 스튜디오에서 확인합니다.</p></div></article>
      <article className="legacy-trend-account"><h3>계좌 · 실행 상태</h3><div className="legacy-trend-content"><p>• 기준 연결: {source.toUpperCase()}<br />• 청산 완료 성과: {closed}건<br />• 공개 시장 데이터와 계좌 잔고는 분리되며, 잔고·포지션은 거래소 탭의 실시간 새로고침 결과를 기준으로 합니다.</p></div></article>
    </div>
  </section>;
}

export function AssetInfoWorkspace({ client, service, source, enabledSources = [] }: { client: GatewayClient; service: "blockchain" | "stock"; source: string; enabledSources?: string[] }) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [query, setQuery] = useState("");
  const [appliedQuery, setAppliedQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [actionMessage, setActionMessage] = useState("");
  const [stockMode, setStockMode] = useState<"all" | "stock" | "etf">("all");
  const [stockAnalyses, setStockAnalyses] = useState<Record<string, any>[]>([]);
  const [stockProfile, setStockProfile] = useState<{ recent_codes: string[]; favorites: string[]; watchlist: string[] }>({ recent_codes: [], favorites: [], watchlist: [] });
  const [stockSuggestions, setStockSuggestions] = useState<Record<string, any>[]>([]);
  const [coinAnalysis, setCoinAnalysis] = useState<Record<string, any> | null>(null);

  function applyStockProfile(payload: Record<string, any>) {
    const symbols = (value: unknown) => Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
    setStockProfile({
      recent_codes: symbols(payload.recent_codes),
      favorites: symbols(payload.favorites),
      watchlist: symbols(payload.watchlist),
    });
  }

  async function updateStockProfile(action: "recent_add" | "favorite_toggle" | "watchlist_add", symbol: string) {
    try {
      const next = await client.updateStockSearchProfile(action, symbol);
      applyStockProfile(next);
      if (action === "favorite_toggle") {
        setActionMessage(next.favorites?.includes(symbol) ? `${symbol} 즐겨찾기에 추가했습니다.` : `${symbol} 즐겨찾기에서 해제했습니다.`);
      } else if (action === "watchlist_add") {
        setActionMessage(next.changed === false ? `${symbol}은(는) 이미 자동매매 감시목록에 있습니다.` : `${symbol}을(를) 자동매매 감시목록에 추가했습니다.`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "종목 검색 설정을 저장하지 못했습니다.");
    }
  }

  function refresh() {
    setLoading(true);
    const feature = service === "stock" ? "stock.info" : "blockchain.coin_info";
    client.workspace(service, feature, source)
      .then((next) => { setSnapshot(next); setError(""); })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : `${service === "stock" ? "종목" : "코인"} 정보를 불러오지 못했습니다.`))
      .finally(() => setLoading(false));
  }

  useEffect(() => { refresh(); }, [client, service, source]);
  useEffect(() => {
    if (service !== "stock") return;
    client.stockSearchProfile().then(applyStockProfile).catch(() => undefined);
  }, [client, service]);
  useEffect(() => {
    if (service !== "stock") return;
    const brokers = Array.from(new Set(enabledSources.filter((item) => STOCK_SOURCES.includes(item))));
    const targets = brokers.length ? brokers : [source || "kiwoom"];
    const timer = window.setTimeout(() => {
      Promise.allSettled(targets.map((broker) => client.stockSuggestions(broker, query.trim(), stockMode)))
        .then((settled) => {
          const seen = new Set<string>();
          const merged = settled.flatMap((result) => result.status === "fulfilled" && Array.isArray(result.value.suggestions) ? result.value.suggestions : [])
            .filter((item) => {
              const code = String(item?.code ?? "");
              if (!code || seen.has(code)) return false;
              seen.add(code);
              return true;
            }).slice(0, 8);
          setStockSuggestions(merged);
        });
    }, 160);
    return () => window.clearTimeout(timer);
  }, [client, enabledSources, query, service, source, stockMode]);
  const requested = useMemo(() => new Set(appliedQuery.toUpperCase().split(/[\s,]+/).filter(Boolean)), [appliedQuery]);
  const rows = (snapshot?.selected_coins ?? []).filter((row) => {
    if (!requested.size) return true;
    return requested.has(String(row.symbol ?? row.coin ?? "").toUpperCase());
  });
  const fallbackSelection = rows.length > 0 && rows.every((row) => ["fallback_unscored", "stale_unscored"].includes(String(row.selection_status ?? "scored")));
  const partialSelection = rows.length > 0 && !fallbackSelection && rows.some((row) => String(row.selection_status ?? "scored") === "scored_partial");
  const analyzedRows = appliedQuery ? rows : [];

  async function runCoinAnalysis() {
    const normalized = query.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!normalized) {
      setError("분석할 코인 심볼을 입력하세요.");
      return;
    }
    setLoading(true); setError(""); setActionMessage(""); setCoinAnalysis(null); setAppliedQuery(normalized);
    try {
      const response = await client.runtimeCommand("coins.analyze", source || "binance", false, normalized);
      const result = (response.result ?? {}) as Record<string, any>;
      setCoinAnalysis({ symbol: result.symbol ?? normalized, ...((result.analysis ?? {}) as Record<string, any>) });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "실시간 코인 분석에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function runCoinSelection() {
    setLoading(true); setActionMessage("코인을 선정하고 있습니다...");
    try {
      const response = await client.runtimeCommand("coins.select", source || "binance");
      const result = (response.result ?? {}) as Record<string, any>;
      const status = String(result.selection_status ?? "scored");
      const selectedCount = Number(result.selected_count ?? 0);
      const eligibleCount = Number(result.execution_eligible_count ?? selectedCount);
      if (status === "stale_data") {
        setActionMessage(`후보 스냅샷 만료: 참조 심볼 ${selectedCount}개 · 기존 정상 후보 유지 또는 신규 주문 차단`);
      } else if (status === "data_unavailable") {
        setActionMessage(`후보 데이터 평가 불가: 참조 심볼 ${selectedCount}개 표시 · 신규 주문 0개`);
      } else if (status === "scored_partial") {
        setActionMessage(`코인 부분 선정 완료: 정상 평가 ${eligibleCount}개 · 목표 수량 미달`);
      } else {
        setActionMessage(`코인 선정 완료: 정상 평가 ${eligibleCount}개`);
      }
      refresh();
    } catch (reason) {
      setActionMessage(reason instanceof Error ? reason.message : "코인 선정 실행에 실패했습니다.");
      setLoading(false);
    }
  }

  async function runStockAnalysis(symbol = query) {
    const normalized = symbol.trim().replace(/[^0-9]/g, "");
    if (normalized.length < 5 || normalized.length > 8) {
      setError("종목코드 5~8자리를 입력하세요.");
      return;
    }
    setQuery(normalized); setAppliedQuery(normalized); setLoading(true); setActionMessage("");
    client.updateStockSearchProfile("recent_add", normalized).then(applyStockProfile).catch(() => undefined);
    try {
      const brokers = Array.from(new Set(enabledSources.filter((item) => STOCK_SOURCES.includes(item))));
      const targets = brokers.length ? brokers : [source || "kiwoom"];
      const settled = await Promise.allSettled(targets.map(async (broker): Promise<Record<string, any>> => {
        const response = await client.runtimeCommand("stocks.analyze", broker, false, normalized);
        const result = (response.result ?? {}) as Record<string, any>;
        const analysis = (result.analysis ?? {}) as Record<string, any>;
        return {
          ...analysis,
          symbol: analysis.code ?? analysis.symbol ?? normalized,
          close: analysis.current_price,
          change: analysis.change_rate,
          source: result.source ?? broker,
        };
      }));
      const analyses = settled.flatMap((result) => result.status === "fulfilled" ? [result.value] : [])
        .filter((analysis) => stockMode === "all" || (stockMode === "etf") === Boolean(analysis.is_etf));
      setStockAnalyses(analyses);
      if (analyses.length) {
        setError("");
      } else {
        const firstFailure = settled.find((result) => result.status === "rejected");
        const detail = firstFailure?.status === "rejected" && firstFailure.reason instanceof Error ? firstFailure.reason.message : "해당 종목을 찾을 수 없습니다.";
        setError(`${stockMode === "all" ? "현재 통합 보기" : stockMode === "stock" ? "현재 주식만 보기" : "현재 ETF만 보기"}에서 종목코드 '${normalized}'를 찾을 수 없습니다. ${detail}`);
      }
    } catch (reason) {
      setStockAnalyses([]);
      setError(reason instanceof Error ? reason.message : "종목 분석 데이터를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  if (service === "stock") {
    const recentTrades = snapshot?.trading?.recent_trades ?? [];
    return <section className="legacy-stock-info-workspace">
      <header className="legacy-stock-info-title">종목/ETF 검색 &amp; 분석 ({stockMode === "all" ? "통합" : stockMode === "stock" ? "주식만" : "ETF만"})</header>
      <div className="legacy-stock-search">
        <label>종목코드 검색</label>
        <input value={query} placeholder="예: 005930, 069500" onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void runStockAnalysis()} />
        <button type="button" onClick={() => void runStockAnalysis()} disabled={loading}>{loading ? "분석 중…" : "검색"}</button>
        <label className="legacy-stock-mode">보기 모드<select value={stockMode} onChange={(event) => setStockMode(event.target.value as "all" | "stock" | "etf")}><option value="all">통합</option><option value="stock">주식만</option><option value="etf">ETF만</option></select></label>
      </div>
      <div className="legacy-stock-quick">
        <b>⭐ 즐겨찾기</b>
        {stockProfile.favorites.length ? stockProfile.favorites.slice(0, 6).map((symbol) => <button key={`favorite-${symbol}`} type="button" onClick={() => void runStockAnalysis(symbol)}>{symbol}</button>) : <span>없음</span>}
        <i aria-hidden="true" />
        <b>최근검색</b>
        {stockProfile.recent_codes.length ? stockProfile.recent_codes.slice(0, 6).map((symbol) => <button key={`recent-${symbol}`} type="button" onClick={() => void runStockAnalysis(symbol)}>{symbol}</button>) : <span>없음</span>}
      </div>
      <div className="legacy-stock-suggestions"><b>자동완성</b>{stockSuggestions.length ? stockSuggestions.map((item) => <button key={`${String(item.broker)}:${String(item.code)}`} type="button" onClick={() => void runStockAnalysis(String(item.code))}>{String(item.code)} {String(item.name ?? item.code).slice(0, 8)} ({item.is_etf ? "ETF" : "주식"})</button>) : <span>추천 없음</span>}</div>
      <article className="legacy-stock-note"><h3>NoahAI 증권 사용 방식</h3><p>증권 탭은 종목 검색·분석·설명 중심으로 동작합니다.<br />조절 요청과 판단 해석은 AI 어시스턴트를 사용하세요.</p></article>
      {(error || actionMessage) && <div className={`inline-notice ${error ? "error-text" : ""}`}>{error || actionMessage}</div>}
      <article className="legacy-stock-analysis">
        <div className="legacy-section-title compact">분석 결과</div>
        {stockAnalyses.length ? <div className="legacy-stock-analysis-list">{stockAnalyses.map((stockAnalysis) => {
          const symbol = String(stockAnalysis.symbol ?? "");
          const favorite = stockProfile.favorites.includes(symbol);
          const watched = stockProfile.watchlist.includes(symbol);
          return <div className="legacy-stock-analysis-row" key={`${String(stockAnalysis.source)}:${symbol}`}>
            <div className="legacy-stock-analysis-title">
              <div><b>{stockAnalysis.name ? `${stockAnalysis.name} (${symbol})` : symbol} - {stockAnalysis.is_etf ? "ETF" : "주식"}</b><em>{String(stockAnalysis.source ?? source).toUpperCase()}</em></div>
              <div className="legacy-stock-card-actions">
                <button type="button" className={favorite ? "active" : ""} onClick={() => void updateStockProfile("favorite_toggle", symbol)}>{favorite ? "★ 즐겨찾기" : "☆ 즐겨찾기"}</button>
                <button type="button" disabled={watched} onClick={() => void updateStockProfile("watchlist_add", symbol)}>{watched ? "감시목록 등록됨" : "자동매매 추가"}</button>
              </div>
            </div>
            <div className="legacy-stock-market-line"><span>현재가 <strong>{numberText(stockAnalysis.close, 0)}원</strong></span><span className={stockAnalysis.change >= 0 ? "positive" : "negative"}>등락률 {stockAnalysis.change >= 0 ? "+" : ""}{numberText(stockAnalysis.change, 2)}%</span><span>거래량 {stockAnalysis.volume == null || !Number.isFinite(Number(stockAnalysis.volume)) ? "미제공" : numberText(stockAnalysis.volume, 0)}</span></div>
            <div className="legacy-stock-score-line"><b>AI 판단 점수 {numberText(stockAnalysis.score, 1)}</b><span>{String(stockAnalysis.reasoning ?? `${String(stockAnalysis.source ?? source).toUpperCase()} 증권사 분석`)}</span></div>
          </div>;
        })}</div> : <div className="empty-state">종목코드를 검색하면 활성 증권사의 기존 StockAnalysisService가 시세·지표·AI 점수를 분석합니다.</div>}
      </article>
      <article className="legacy-stock-activity"><div className="legacy-section-title compact">내 보유·최근 체결 종목</div>{recentTrades.length ? recentTrades.slice(0, 8).map((row, index) => <div className="legacy-stock-activity-row" key={String(row.id ?? index)}><b>{String(row.symbol ?? row.code ?? "—")}</b><span>{String(row.side ?? row.type ?? "—")}</span><span>{String(row.exit_time ?? row.created_at ?? "")}</span></div>) : <div className="empty-state">저장된 주식/ETF 체결 기록이 없습니다.</div>}</article>
      <div className="legacy-stock-preview-header"><span>브로커</span><span>종목</span><span>구분</span><span>현재가</span><span>등락률</span><span>거래량</span><span>비고</span></div>
      <article className="legacy-stock-preview"><div className="legacy-section-title compact">시장 종목 미리보기 · 검색용 ({stockMode === "all" ? "통합" : stockMode === "stock" ? "주식만" : "ETF만"})</div><div className="empty-state">종목을 검색하면 확인된 시세가 이 화면에 표시됩니다. 코인 후보 데이터는 사용하지 않습니다.</div></article>
      <div className="legacy-coin-actions"><button className="legacy-refresh-button" type="button" onClick={refresh} disabled={loading}>종목 정보 새로고침</button></div>
    </section>;
  }

  return <section className="legacy-coin-workspace">
    <header className="legacy-coin-heading">선택된 거래 코인 정보 (AI 평가 결과)</header>
    <div className="legacy-coin-search">
      <label>심볼 직접 분석</label>
      <input value={query} placeholder="예: BTCUSDT, ETHUSDT" onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === "Enter" && void runCoinAnalysis()} />
      <button type="button" onClick={() => void runCoinAnalysis()} disabled={loading}>{loading ? "분석 중…" : "분석"}</button>
      <span>NoahAI가 실시간 분석합니다</span>
    </div>
    <div className="legacy-coin-notices" role="status" aria-live="polite">
      {(error || actionMessage) && <div className={`inline-notice ${error ? "error-text" : ""}`}>{error || actionMessage}</div>}
      {fallbackSelection && <div className="inline-notice warning-text">후보 데이터를 평가하지 못해 고정 참조 심볼을 표시합니다. 점수는 0이 아니라 미산출이며, 이 목록의 PAPER·LIVE 신규 주문은 차단됩니다. 기존 포지션 보호는 계속되며 연결·티커·캔들 데이터 회복 후 다시 선정하세요.</div>}
      {partialSelection && <div className="inline-notice warning-text">목표 수량은 채우지 못했지만 정상적으로 점수를 산출한 후보만 부분 선정했습니다. 고정 목록으로 바꾸지 않으며, 각 후보는 후속 실시간 신호·전략·가드레일을 다시 통과해야 합니다.</div>}
      <div className="inline-notice">코인 선정은 분석 후보를 좁히는 단계입니다. 정상 선정되어도 시장·전략 조건이 맞지 않으면 실시간 판단은 HOLD로 남으며 주문을 보장하지 않습니다.</div>
    </div>
    <article className="legacy-coin-analysis-result">
      <div className="legacy-section-title compact">코인 분석 결과</div>
      <div className="legacy-coin-analysis-body">
        {coinAnalysis && <div className="legacy-coin-analysis-card live" key={String(coinAnalysis.symbol)}><b>{String(coinAnalysis.symbol)} 코인 분석</b><span>현재가 {numberText(coinAnalysis.current_price, 4)}<br />신호 <strong className={String(coinAnalysis.signal).toUpperCase() === "LONG" ? "positive" : String(coinAnalysis.signal).toUpperCase() === "SHORT" ? "negative" : "warning"}>{String(coinAnalysis.signal ?? "HOLD")}</strong> · 신뢰도 {numberText(Number(coinAnalysis.confidence ?? 0) * 100, 1)}%</span><span>트렌드 {String(coinAnalysis.trend ?? "N/A")} · 변동성 {numberText(coinAnalysis.volatility, 2)}%{coinAnalysis.reasoning ? <><br />{String(coinAnalysis.reasoning).slice(0, 220)}</> : null}</span></div>}
        {!coinAnalysis && analyzedRows.map((row, index) => <div className="legacy-coin-analysis-card" key={String(row.id ?? `${row.symbol}-${index}`)}><b>{String(row.symbol ?? row.coin ?? "—")}</b><span>AI 종합점수 {numberText(row.overall_score)}</span><span>기술 {numberText(row.technical_score)} · 트렌드 {numberText(row.trend_score)} · 리스크 {numberText(row.risk_score)}</span></div>)}
        {appliedQuery && !coinAnalysis && !analyzedRows.length && !loading && !error && <div className="empty-state">실시간 분석 결과를 가져올 수 없습니다. 거래소 연결 상태와 심볼을 확인하세요.</div>}
      </div>
    </article>
    <div className="legacy-coin-table-header">
        <span>코인</span><span>AI종합점수</span><span>변동성점수</span><span>거래량점수</span><span>기술점수</span><span>트렌드점수</span><span>리스크점수</span>
    </div>
    <article className="legacy-coin-result"><div className="legacy-coin-table-body">
        {rows.map((row, index) => {
          const scoreAvailable = row.overall_score !== null && row.overall_score !== undefined && Number.isFinite(Number(row.overall_score));
          const overall = scoreAvailable ? Number(row.overall_score) : null;
          return <div className="legacy-coin-row" key={String(row.id ?? `${row.symbol}-${index}`)}>
            <b>{String(row.symbol ?? row.coin ?? "—")}</b>
            <strong className={overall == null ? "warning" : overall >= 70 ? "positive" : overall >= 50 ? "warning" : "negative"}>{overall == null ? "미산출" : numberText(overall)}</strong>
            <span>{metricText(row.volatility_score)}</span><span>{metricText(row.volume_score)}</span><span>{metricText(row.technical_score)}</span><span>{metricText(row.trend_score)}</span><span>{metricText(row.risk_score)}</span>
          </div>;
        })}
        {!loading && !rows.length && <div className="empty-state legacy-selection-empty"><span>선정된 코인이 없습니다.</span><span>• 아래 '코인 선정 실행' 버튼을 누르거나</span><span>• 자동매매를 시작하면 자동으로 코인이 선정됩니다.</span></div>}
        {loading && <div className="empty-state">코인 평가 결과를 불러오는 중입니다.</div>}
      </div></article>
    <div className="legacy-coin-actions"><button className="legacy-select-button" type="button" onClick={runCoinSelection} disabled={loading}>코인 선정 실행</button><button className="legacy-refresh-button" type="button" onClick={refresh} disabled={loading}>코인 정보 새로고침</button></div>
  </section>;
}

export function SourceWorkspace({ client, runtime, service, source, onOpenManual, onOpenSettings, onRuntimeChanged }: { client: GatewayClient; runtime: RuntimeSnapshot | null; service: "blockchain" | "stock"; source: string; onOpenManual: () => void; onOpenSettings: () => void; onRuntimeChanged: () => Promise<void> | void }) {
  const [workspace, setWorkspace] = useState<WorkspaceSnapshot | null>(null);
  const [logs, setLogs] = useState<Array<{ source: string; message: string; level?: string; exchange?: string; category?: string }>>([]);
  const [accountPayload, setAccountPayload] = useState<Record<string, any> | null>(null);
  const [message, setMessage] = useState("");
  const [accountBusy, setAccountBusy] = useState(false);
  const [commandBusy, setCommandBusy] = useState(false);
  const [simpleOnly, setSimpleOnly] = useState(false);
  const [analysisOnly, setAnalysisOnly] = useState(false);
  const [hideInit, setHideInit] = useState(false);
  const [hideDebug, setHideDebug] = useState(false);
  const [hideSystem, setHideSystem] = useState(false);
  const [logHelpOpen, setLogHelpOpen] = useState(false);
  const [paperHistoryOpen, setPaperHistoryOpen] = useState(false);
  const [historyFetchFailed, setHistoryFetchFailed] = useState(false);
  const clearMarkerRef = useRef("");
  const sourceLogConsoleRef = useRef<HTMLDivElement | null>(null);
  const running = runtime?.running_sources.includes(source) ?? false;
  const enabled = runtime?.enabled_sources.includes(source) ?? false;
  const credentialsConfigured = runtime?.credential_status?.[source] ?? false;
  const sourceExecutionMode = String(
    runtime?.execution_modes?.[source]
      ?? (runtime?.paper_trading === true ? "paper" : runtime?.live_trading === true ? "live" : "learning"),
  ).toLowerCase();
  const liveMode = sourceExecutionMode === "live";
  const paperMode = sourceExecutionMode === "paper";
  const executionModeLabel = liveMode ? "LIVE" : paperMode ? "PAPER" : "LEARNING";
  useEffect(() => {
    // 기관/모드 전환 시 LIVE와 PAPER 내역 모두 요약 상태로 시작한다.
    setPaperHistoryOpen(false);
  }, [sourceExecutionMode, source]);

  function refreshStored() {
    Promise.all([
      client.workspace(service, `${service}.source_workspaces`, source),
      credentialsConfigured
        ? client.logs(service, source, 100)
        : Promise.resolve({ schema_version: "1.0.0", service, source, lines: [], captured_at: new Date().toISOString() }),
    ])
      .then(([nextWorkspace, nextLogs]) => {
        setWorkspace(nextWorkspace);
        setHistoryFetchFailed(false);
        const markerIndex = clearMarkerRef.current ? nextLogs.lines.map((line) => line.message).lastIndexOf(clearMarkerRef.current) : -1;
        setLogs(markerIndex >= 0 ? nextLogs.lines.slice(markerIndex + 1) : nextLogs.lines);
        setMessage("");
      })
      .catch((reason: unknown) => {
        setHistoryFetchFailed(true);
        setMessage(reason instanceof Error ? reason.message : `${service === "stock" ? "증권사" : "거래소"} 화면을 불러오지 못했습니다.`);
      });
  }
  useEffect(() => {
    setAccountPayload(null);
    refreshStored();
    if (credentialsConfigured) {
      let active = true;
      setAccountBusy(true);
      client.refreshAccounts([source], true)
        .then((next) => {
          if (active) {
            setAccountPayload(next);
            setMessage(accountConnectionFailure(next, source));
          }
        })
        .catch((reason: unknown) => {
          if (!active) return;
          setAccountPayload({ sources: { [source]: { source, status: "error" } } });
          setMessage(reason instanceof Error ? reason.message : "실시간 계좌 조회에 실패했습니다.");
        })
        .finally(() => { if (active) setAccountBusy(false); });
      return () => { active = false; };
    }
  }, [client, service, source, credentialsConfigured]);
  useEffect(() => {
    if (!credentialsConfigured) return;
    let active = true;
    const refreshAccount = () => client.refreshAccounts([source], false)
        .then((next) => {
          if (active) {
            setAccountPayload(next);
            setMessage(accountConnectionFailure(next, source));
          }
        })
        .catch(() => { /* Keep the last valid snapshot; the card exposes component failure state. */ });
    const stop = startSequentialPoll(refreshAccount, 7_000, { immediate: false });
    return () => { active = false; stop(); };
  }, [client, source, credentialsConfigured]);
  useEffect(() => {
    if (!credentialsConfigured) return;
    let active = true;
    const loadLogs = () => client.logs(service, source, 200).then((nextLogs) => {
      if (!active) return;
      const markerIndex = clearMarkerRef.current ? nextLogs.lines.map((line) => line.message).lastIndexOf(clearMarkerRef.current) : -1;
      setLogs(markerIndex >= 0 ? nextLogs.lines.slice(markerIndex + 1) : nextLogs.lines);
    }).catch(() => { /* Keep the last source snapshot while the next poll retries. */ });
    const loadWorkspace = () => client.workspace(service, `${service}.source_workspaces`, source).then((nextWorkspace) => {
      if (active) { setWorkspace(nextWorkspace); setHistoryFetchFailed(false); }
    }).catch(() => { if (active) setHistoryFetchFailed(true); });
    const stopLogs = startSequentialPoll(loadLogs, 1_000);
    const stopWorkspace = startSequentialPoll(loadWorkspace, 5_000);
    return () => { active = false; stopLogs(); stopWorkspace(); };
  }, [client, service, source, credentialsConfigured]);

  async function refreshAccount() {
    if (!credentialsConfigured) {
      setMessage(`${source.toUpperCase()} API 키를 설정한 뒤 연결을 확인하세요.`);
      return;
    }
    setAccountBusy(true); setMessage("");
    try {
      const next = await client.refreshAccounts([source], true);
      setAccountPayload(next);
      setMessage(accountConnectionFailure(next, source));
    }
    catch (reason) {
      setAccountPayload({ sources: { [source]: { source, status: "error" } } });
      setMessage(reason instanceof Error ? reason.message : "실시간 계좌 조회에 실패했습니다.");
    }
    finally { setAccountBusy(false); }
  }
  async function command(action: "start" | "stop") {
    const learningMode = !liveMode && !paperMode;
    const wording = learningMode
      ? action === "start" ? "분석·학습 시작" : "분석·학습 정지"
      : action === "start" ? "거래 시작" : "거래 정지";
    if (!credentialsConfigured) {
      setMessage(`${source.toUpperCase()} API 키를 설정한 뒤 연결을 확인하세요.`);
      return;
    }
    if (!enabled) {
      setMessage(`${source.toUpperCase()} 사용을 설정에서 먼저 켜세요.`);
      return;
    }
    const confirmation = action === "start" && liveMode
      ? `${source.toUpperCase()} LIVE 자동매매를 시작할까요?\n\nPAPER가 아닙니다. 실제 주문이 제출될 수 있습니다. API 주문 권한·주문 대상 범위·보유 포지션을 다시 확인하세요.`
      : `${source.toUpperCase()} ${action === "start" ? learningMode ? "LEARNING 분석·학습" : `${executionModeLabel} 자동매매` : wording} 명령을 실행할까요?`;
    if (!window.confirm(confirmation)) return;
    setCommandBusy(true); setMessage("");
    try {
      await client.runtimeCommand(`trading.${action}`, source, false, "", action === "start" && liveMode);
      setMessage(`${executionModeLabel} ${wording} 명령을 엔진에 전달했습니다.`);
      try { await onRuntimeChanged(); }
      catch (_) { setMessage(`${wording}은 완료됐지만 화면 상태 재조회가 지연되고 있습니다. 자동 갱신을 기다리세요.`); }
      refreshStored();
    }
    catch (reason) { setMessage(reason instanceof Error ? reason.message : `${wording} 명령에 실패했습니다.`); }
    finally { setCommandBusy(false); }
  }

  const account = sourceAccount(accountPayload, source);
  const accountView = accountConnectionView(account, source);
  const accountConnected = accountView.connected;
  const accountChecked = Boolean(account);
  const accountFailed = accountChecked && !accountConnected;
  const trading = workspace?.trading;
  const sourceStatistics = workspace?.trading_statistics;
  const stockStatistics = workspace?.stock_trading_statistics?.brokers.find((row) => row.broker.toLowerCase() === source.toLowerCase())
    ?? workspace?.stock_trading_statistics?.brokers[0];
  const accountPositions = Array.isArray(account?.positions) ? account?.positions : [];
  const paperPositions = Array.isArray(workspace?.paper_positions)
    ? workspace.paper_positions
    : Array.isArray(account?.paper_positions) ? account.paper_positions : [];
  const paperPositionsStatus = String(
    workspace?.paper_positions_status ?? account?.paper_positions_status ?? "pending",
  );
  const paperPositionView = paperMode && paperPositionsStatus === "success";
  const positions = paperPositionView ? paperPositions : accountPositions;
  const paperPositionLimit = Math.max(1, Number(workspace?.paper_position_policy?.limit ?? 3));
  const paperPositionModeLabel = workspace?.paper_position_policy?.mode === "focus" ? "집중" : "다중";
  const paperPositionLimitExceeded = paperPositionView && positions.length > paperPositionLimit;
  const openOrders = Array.isArray(account?.open_orders) ? account?.open_orders : [];
  const positionsStatus = paperPositionView
    ? paperPositionsStatus
    : String(account?.positions_status ?? (accountConnected ? "success" : account?.status ?? "pending"));
  const positionsHealthy = positionsStatus === "success";
  const balanceRows = normalizedBalanceRows(account, service, source);
  const primaryAsset = service === "stock" ? "예수금" : ["upbit", "bithumb", "coinone"].includes(source.toLowerCase()) ? "KRW" : "USDT";
  const balanceCards = Array.from({ length: 3 }, (_, index) => balanceRows[index] ?? { asset: index === 0 ? primaryAsset : "보유자산", value: null });
  const accumulatedFees = sourceStatistics
    ? Object.values(sourceStatistics.fees_by_currency ?? {}).reduce((sum, value) => sum + Number(value ?? 0), 0)
    : (workspace?.statistics ?? []).reduce((sum, row) => sum + Number(row.fee ?? row.fees ?? row.commission ?? 0), 0);
  const sourceExecutionCount = Number(sourceStatistics?.execution_count ?? 0);
  const sourceClosedCount = Number(sourceStatistics?.closed_count ?? trading?.closed_count ?? 0);
  const sourceWinRate = Number(sourceStatistics?.win_rate ?? trading?.win_rate ?? 0);
  const sourceCurrency = service === "stock" || ["upbit", "bithumb", "coinone"].includes(source.toLowerCase()) ? "KRW" : "USDT";
  const sourcePnl = Number(sourceStatistics?.pnl_by_currency?.[sourceCurrency] ?? trading?.pnl_by_currency?.[sourceCurrency] ?? 0);
  const paperStatistics = workspace?.paper_statistics;
  const membershipAccess = workspace?.membership_access;
  const runtimeCustomStrategies = Array.isArray(workspace?.active_custom_strategies)
    ? workspace.active_custom_strategies : [];
  const appliedCustomStrategies = runtimeCustomStrategies.filter(
    (row) => String(row.operation_mode ?? "").toLowerCase() !== "paper_validation",
  );
  const observingCustomStrategies = runtimeCustomStrategies.filter(
    (row) => String(row.operation_mode ?? "").toLowerCase() === "paper_validation",
  );
  const appliedCustomStrategyNames = appliedCustomStrategies.slice(0, 2).map(
    (row) => String(row.name ?? row.strategy_key ?? row.version_id ?? "사용자 전략"),
  ).join(", ");
  const paperClosedCount = Number(paperStatistics?.closed_count ?? 0);
  const paperWinRate = paperStatistics?.win_rate == null ? null : Number(paperStatistics.win_rate);
  const paperPnl = Number(paperStatistics?.pnl_by_currency?.[sourceCurrency] ?? paperStatistics?.net_pnl ?? 0);
  const paperFees = Number(paperStatistics?.fees_by_currency?.[sourceCurrency] ?? paperStatistics?.fees ?? 0);
  const paperUnverifiedCount = Number(paperStatistics?.unverified_count ?? 0);
  const sourceLabel = source.toUpperCase();
  const learningMode = !liveMode && !paperMode;
  const controlStateText = learningMode
    ? running ? "LEARNING 분석·학습 실행 중 · 신규 주문 차단" : "LEARNING 대기 · 시작 버튼 필요"
    : running ? `${executionModeLabel} 자동매매 실행 중` : `자동매매 정지 · ${executionModeLabel} 설정`;
  const connectionText = !credentialsConfigured
    ? "API 키 연결 필요"
    : accountConnected
      ? accountView.label
      : accountFailed
        ? accountView.label
        : enabled
          ? "API 키 설정됨 · 연결 확인 중"
          : "API 키 설정됨 · 사용 꺼짐";
  const connectionClass = !credentialsConfigured || accountFailed
    ? "source-connection-status error"
    : accountConnected
      ? "source-connection-status live"
      : "source-connection-status waiting";
  const isCryptoSpot = service === "blockchain" && ["upbit", "bithumb", "coinone"].includes(source.toLowerCase());
  const isSpotHoldings = !paperPositionView && (service === "stock" || isCryptoSpot);
  const spotHoldingSummary = account?.spot_holding_summary ?? {};
  const positionNoun = isSpotHoldings ? "보유" : "활성";
  const positionEmptyText = paperPositionView ? "활성 가상 포지션 없음" : service === "stock" ? "보유 종목 없음" : isSpotHoldings ? "보유자산 없음" : "활성 포지션 없음";
  const positionHeaderText = !credentialsConfigured
    ? "API 키 연결 후 조회"
    : !accountChecked
      ? "조회 중"
      : !positionsHealthy
        ? "조회 오류 · 수량 미확정"
        : paperPositionView
          ? paperPositionLimitExceeded
            ? `PAPER · ${positions.length}개 활성 / 상한 ${paperPositionLimit} · 신규 진입 차단`
            : `PAPER · ${positions.length}개 활성 / ${paperPositionModeLabel} 상한 ${paperPositionLimit}`
        : isCryptoSpot
          ? `계좌 ${Number(spotHoldingSummary.account_total ?? positions.length)}개 · NoahAI ${Number(spotHoldingSummary.noahai_managed ?? 0)}개`
          : `${running ? executionModeLabel : "정지"} · ${positions.length}개 ${positionNoun}`;
  const positionBodyText = !credentialsConfigured
    ? "API 키 연결 후 조회"
    : !accountChecked
      ? (isSpotHoldings ? "보유자산 조회 중" : "포지션 조회 중")
      : positionsHealthy
        ? positionEmptyText
        : "포지션 조회에 실패했습니다. 0개로 간주하지 않습니다.";
  const positionStatusClass = !credentialsConfigured
    ? "position-status warning"
    : !accountChecked
      ? "position-status loading"
      : !positionsHealthy
        ? "position-status error"
        : paperPositionLimitExceeded
          ? "position-status warning"
        : running
          ? "position-status live"
          : "position-status stopped";
  const filteredLogs = logs.filter((line) => {
    const text = `${line.source} ${line.message}`.toLowerCase();
    if (hideInit && /(초기|init|생성 완료|로드 완료)/i.test(text)) return false;
    if (hideDebug && (line.level === "DEBUG" || /debug/i.test(text))) return false;
    if (hideSystem && (line.category === "system" || /(system|ex=global)/i.test(text))) return false;
    if (analysisOnly && line.category !== "analysis" && !/(분석|analysis|signal|rsi|macd|trend)/i.test(text)) return false;
    if (simpleOnly && line.category !== "trade" && !/(error|warning|거래|체결|진입|청산|주문)/i.test(text)) return false;
    return true;
  });
  useEffect(() => {
    const consoleElement = sourceLogConsoleRef.current;
    if (consoleElement) consoleElement.scrollTop = consoleElement.scrollHeight;
  }, [filteredLogs.length, source]);

  return <section className="legacy-exchange-workspace">
    <div className="legacy-exchange-left">
      <article className="legacy-exchange-card exchange-control">
        <header className="source-card-header"><div className="source-card-title"><span className="source-card-mark control" aria-hidden="true">C</span><div><small>{service === "stock" ? "BROKER CONTROL" : "EXCHANGE CONTROL"}</small><h3>{sourceLabel} 제어</h3></div></div><span className={`source-operation-status ${running ? "live" : "stopped"}`}>{controlStateText}</span></header>
        <div className="exchange-control-actions"><button className={running ? "stop" : "start"} disabled={commandBusy || !enabled || !credentialsConfigured} type="button" onClick={() => command(running ? "stop" : "start")}>{commandBusy ? "⏳ 처리 중" : learningMode ? running ? `■ ${sourceLabel} 분석·학습 정지` : `▶ ${sourceLabel} 분석·학습 시작` : running ? `■ ${sourceLabel} 거래 정지` : `▶ ${sourceLabel} 거래 시작`}</button>{service === "stock" && <button className="refresh" disabled={accountBusy || !credentialsConfigured} type="button" onClick={refreshAccount}>새로고침</button>}<div className={connectionClass}><i aria-hidden="true" /><strong>{connectionText}</strong></div></div>
        {membershipAccess?.allowed === false && <div className="membership-source-status" role="status"><strong>거래 권한 승인 필요 · {sourceLabel}</strong><span>{membershipAccess.label}. daltrading에서 승인 상태를 확인하거나 관리자에게 승인을 요청하세요. API 인증과 거래 권한은 별개입니다.</span></div>}
        {!credentialsConfigured ? <button className="inline-settings-link" type="button" onClick={onOpenSettings}>설정에서 API 연결하기</button> : paperMode ? <div className={`runtime-strategy-status ${appliedCustomStrategies.length ? "applied" : observingCustomStrategies.length ? "observing" : "empty"}`} role="status"><strong>{appliedCustomStrategies.length ? `전략 스튜디오 적용: ${appliedCustomStrategyNames}` : observingCustomStrategies.length ? `PAPER 전진검증 후보 ${observingCustomStrategies.length}개` : "전략 스튜디오 실행 풀 없음"}</strong><span>{appliedCustomStrategies.length ? `적용 중 버전은 PAPER에서 자동 실행 · 재적용 불필요${observingCustomStrategies.length ? ` · 전진검증 후보 ${observingCustomStrategies.length}개 별도` : ""}` : observingCustomStrategies.length ? "최종 적용 전략과 별도 PAPER 검증 중" : "현재 적용·검증 전략이 없습니다. 기본 NoahAI PAPER 운용은 계속됩니다."}</span></div> : <small>전략 스튜디오 사용 여부는 설정의 실행 계약을 따릅니다.</small>}
      </article>
      <article className="legacy-exchange-card exchange-balances"><header className="source-card-header"><div className="source-card-title"><span className="source-card-mark balance" aria-hidden="true">₩</span><div><small>ACCOUNT BALANCE</small><h3>잔고</h3></div></div><div className="exchange-account-actions"><span className={`account-refresh-status ${accountConnected ? "live" : accountFailed || !credentialsConfigured ? "warning" : "loading"}`}>{!credentialsConfigured ? "API 키 연결 필요" : accountConnected ? `${sourceLabel} · 7초 자동 갱신` : accountFailed ? accountView.balanceLabel : "연결 확인 중"}</span><button className="account-refresh-button" type="button" onClick={refreshAccount} disabled={accountBusy || !credentialsConfigured}>{accountBusy ? "조회 중…" : "실시간 새로고침"}</button></div></header><div className="legacy-balance-grid">{balanceCards.map((row, index) => <div key={`${row.asset}-${index}`}><span>{row.asset}</span><b>{row.value === null ? (!credentialsConfigured ? (index === 0 ? "API 키 연결 필요" : "연결 후 조회") : accountFailed ? accountView.balanceLabel : index === 0 ? "조회 중" : "추가 자산 없음") : numberText(row.value, 6)}</b></div>)}</div></article>
      <article className="legacy-exchange-card exchange-positions"><header className="source-card-header"><div className="source-card-title"><span className="source-card-mark position" aria-hidden="true">P</span><div><small>{paperPositionView ? "PAPER POSITIONS" : isSpotHoldings ? "ACCOUNT HOLDINGS" : "OPEN POSITIONS"}</small><h3>{paperPositionView ? "가상 포지션" : isCryptoSpot ? "계좌 보유자산" : isSpotHoldings ? "보유자산" : "포지션"}</h3></div></div><span className={positionStatusClass}>{positionHeaderText}</span></header><div className={paperPositionView ? "paper-position-scroll" : "position-scroll"}>{isCryptoSpot && !paperPositionView && positionsHealthy && <p className="spot-holding-scope">계좌 잔고 전체입니다. NoahAI 원장이 있는 수량만 자동매매가 관리하며 수동·에어드롭·거래불가 자산은 자동 제외합니다.</p>}{positions.map((position: any, index: number) => { const pnl = Number(position.unrealized_pnl ?? position.unrealizedPnl ?? position.pnl ?? position.profit_loss ?? 0); const holdingClass = spotHoldingClass(position); const entryPrice = Number(position.average ?? position.avg_price ?? position.entry_price ?? 0); return <div className={`legacy-position-row ${isCryptoSpot && !paperPositionView ? `spot-${holdingClass.className}` : ""}`} key={String(position.symbol ?? position.asset ?? index)}><div><b>{String(position.symbol ?? position.asset ?? "—")}</b><span>{isCryptoSpot && !paperPositionView ? "보유" : String(position.side ?? position.positionSide ?? (isSpotHoldings ? "보유" : "—"))}</span></div><div><span>수량 {numberText(position.amount ?? position.quantity ?? position.positionAmt ?? position.size, 6)}</span><small>{isCryptoSpot && !paperPositionView ? Number(position.managed_quantity ?? 0) > 0 ? `NoahAI 관리수량 ${numberText(position.managed_quantity, 6)}` : entryPrice > 0 ? `평균가 ${numberText(entryPrice, 4)}` : "평균가 미제공" : isSpotHoldings ? `평균가 ${numberText(entryPrice, 4)}` : `진입가 ${numberText(position.entry_price ?? position.entryPrice, 4)} · ${numberText(position.leverage, 0)}x`}</small></div><div><span>{isCryptoSpot && !paperPositionView ? "자동매매 분류" : isSpotHoldings ? "평가손익" : "미실현 PnL"}</span>{isCryptoSpot && !paperPositionView ? <strong className={`holding-class ${holdingClass.className}`}>{holdingClass.label}</strong> : <strong className={pnl < 0 ? "negative" : pnl > 0 ? "positive" : ""}>{pnl > 0 ? "+" : ""}{numberText(pnl, service === "stock" ? 0 : 4)}{service === "stock" ? "원" : ` ${sourceCurrency}`}</strong>}</div></div>; })}{!positions.length && <div className="empty-state">{positionBodyText}</div>}</div></article>
      <article className="legacy-exchange-card exchange-statistics">
        <header className="source-card-header"><div className="source-card-title"><span className="source-card-mark statistics" aria-hidden="true">↗</span><div><small>{liveMode ? "VERIFIED PERFORMANCE" : paperMode ? "PAPER PERFORMANCE" : "LEARNING STATUS"}</small><h3>{liveMode ? "실거래 통계 · 오늘" : paperMode ? "가상 거래 통계 · 전체" : "학습 실행 상태"}</h3></div></div><div className="source-stat-context"><strong>{sourceLabel}</strong>{paperMode ? <><span>전체 가상 청산 <b>{paperClosedCount}건</b></span>{paperStatistics?.window_limited && <span>기관별 최대 {Number(paperStatistics.recent_window_limit)}건 · 전체 원장 초과</span>}</> : liveMode ? service === "stock" ? <span>오늘 청산 기준</span> : <><span>오늘 거래소 확인 체결 <b>{executionCountLabel(sourceExecutionCount, sourceStatistics?.execution_history_status)}</b></span><span>오늘 NoahAI 청산 <b>{sourceClosedCount}건</b></span></> : <span>신규 주문·가상 체결 없음</span>}</div></header>
        {paperMode ? <><div className="legacy-trade-kpis"><div><span>가상 청산</span><b>{paperClosedCount}건</b></div><div><span>가상 승률</span><b className="positive">{paperWinRate == null ? "미확정" : `${numberText(paperWinRate, 2)}%`}</b></div><div><span>가상 순손익 ({sourceCurrency})</span><b className={paperPnl < 0 ? "negative" : "positive"}>{paperPnl >= 0 ? "+" : ""}{numberText(paperPnl, service === "stock" ? 0 : 4)}</b></div><div><span>가상 수수료 ({sourceCurrency})</span><b>{numberText(paperFees, service === "stock" ? 0 : 4)}</b></div></div>{paperUnverifiedCount > 0 && <p className="spot-holding-scope">구버전 손익 미확정 {paperUnverifiedCount}건은 승률·손익에서 제외했습니다.</p>}</> : liveMode ? service === "stock" ? <div className="legacy-trade-kpis"><div><span>총 거래</span><b>{Number(stockStatistics?.total_trades ?? 0)}건</b></div><div><span>오늘 체결</span><b>{Number(stockStatistics?.today_count ?? 0)}건</b></div><div><span>실현손익</span><b className={Number(stockStatistics?.realized_pnl ?? 0) < 0 ? "negative" : "positive"}>{Number(stockStatistics?.realized_pnl ?? 0) > 0 ? "+" : ""}{numberText(stockStatistics?.realized_pnl ?? 0, 0)}원</b></div><div><span>미체결</span><b>{Number(stockStatistics?.open_orders_count ?? openOrders.length)}건</b></div></div> : <div className="legacy-trade-kpis"><div><span>거래소 체결</span><b>{executionCountLabel(sourceExecutionCount, sourceStatistics?.execution_history_status)}</b></div><div><span>청산 승률</span><b className="positive">{numberText(sourceWinRate, 2)}%</b></div><div><span>청산 순손익</span><b className={sourcePnl < 0 ? "negative" : "positive"}>{sourcePnl >= 0 ? "+" : ""}{numberText(sourcePnl, 4)}</b></div><div><span>청산 수수료</span><b>{numberText(accumulatedFees, 4)}</b></div></div> : <div className="empty-state">{running ? "LEARNING은 분석·전략·가드레일 판단만 기록 중이며 실제 주문과 가상 체결 통계는 만들지 않습니다." : "LEARNING은 자동으로 시작되지 않습니다. 위의 분석·학습 시작 버튼을 누르면 시세·코인 선정·전략·가드레일 판단만 기록하고 신규 주문은 차단합니다."}</div>}
      </article>
      <SourceTradeHistory mode={sourceExecutionMode} source={source} history={workspace?.live_history} loading={!workspace && !historyFetchFailed} failed={historyFetchFailed}>
      <article className={`legacy-exchange-card exchange-statistics paper-history-card ${paperHistoryOpen ? "expanded" : "collapsed"}`}><header className="source-card-header"><div className="source-card-title"><span className="source-card-mark statistics" aria-hidden="true">P</span><div><small>PAPER HISTORY</small><h3>{paperMode ? "현재 PAPER 거래내역" : "과거 PAPER 검증 이력"}</h3></div></div><div className="paper-history-header-actions"><div className="source-stat-context"><strong>PAPER 기록</strong><span>{liveMode ? "LIVE와 분리" : "청산 완료"} · {Number(workspace?.paper_trades?.length ?? 0)}건 · 활성 수와 무관</span></div><button className="paper-history-toggle" type="button" aria-expanded={paperHistoryOpen} onClick={() => setPaperHistoryOpen((value) => !value)}>{paperHistoryOpen ? "접기" : "펼치기"}</button></div></header>{paperHistoryOpen && <>{liveMode && <p className="spot-holding-scope">과거 PAPER 가상 청산 기록입니다. 현재 LIVE 거래나 가상체결 발생을 뜻하지 않습니다.</p>}<div className="legacy-paper-history">{[...(workspace?.paper_trades ?? [])].reverse().slice(0, 10).map((row, index) => { const verified = String(row.calculation_status ?? "valid") === "valid"; return <div className="legacy-position-row" key={String(row.event_id ?? index)}><div><b>{String(row.symbol ?? "—")}</b><span>{String(row.exchange ?? source).toUpperCase()}</span></div><div><span>{row.strategy_key && row.version_id ? "전략 스튜디오" : "기본 전략"}</span><small>{String(row.closed_at ?? "")}</small></div><div><span>가상 실현손익</span>{verified ? <strong className={Number(row.net_pnl ?? 0) < 0 ? "negative" : "positive"}>{Number(row.net_pnl ?? 0) > 0 ? "+" : ""}{numberText(row.net_pnl, service === "stock" ? 0 : 4)} {String(row.quote_currency ?? sourceCurrency)}</strong> : <strong>과거 손익 미확정</strong>}</div></div>; })}{!workspace?.paper_trades?.length && <div className="empty-state">이 거래소에서 완료된 PAPER 가상 청산이 아직 없습니다.</div>}</div></>}</article>
      </SourceTradeHistory>
    </div>
    <article className="legacy-exchange-log legacy-exchange-card">
      <div className="legacy-log-filters">
        <label><input type="checkbox" checked={simpleOnly} onChange={(event) => { setSimpleOnly(event.target.checked); if (event.target.checked) setAnalysisOnly(false); }} />간략 로그</label>
        <label><input type="checkbox" checked={analysisOnly} onChange={(event) => { setAnalysisOnly(event.target.checked); if (event.target.checked) setSimpleOnly(false); }} />분석 과정만</label>
        <label><input type="checkbox" checked={!simpleOnly && !analysisOnly && !hideInit && !hideDebug && !hideSystem} onChange={() => { setSimpleOnly(false); setAnalysisOnly(false); setHideInit(false); setHideDebug(false); setHideSystem(false); }} />전체 로그</label>
        <label><input type="checkbox" checked={hideInit} onChange={(event) => setHideInit(event.target.checked)} />초기화 로그 숨김</label>
        <label><input type="checkbox" checked={hideDebug} onChange={(event) => setHideDebug(event.target.checked)} />디버그 로그 숨김</label>
        <label><input type="checkbox" checked={hideSystem} onChange={(event) => setHideSystem(event.target.checked)} />시스템 로그 숨김</label>
      </div>
      <div className="source-log-connection-slot">{!credentialsConfigured && <div className="inline-notice">{source.toUpperCase()} API 키를 설정한 뒤 연결하세요. 미연결 상태에서는 과거 로그를 현재 연결 기록처럼 표시하지 않습니다.</div>}</div>
      <div className="legacy-log-console" ref={sourceLogConsoleRef}>{filteredLogs.map((line, index) => <div key={`${line.source}:${index}`}><code>{line.message}</code></div>)}{!filteredLogs.length && <div className="empty-state">{credentialsConfigured ? `표시할 ${service === "stock" ? "증권사" : "거래소"} 로그가 없습니다.` : "API 키 연결 필요"}</div>}</div>
      <div className="legacy-log-toolbar compact"><button type="button" onClick={() => setLogHelpOpen(true)}>로그도움말</button><button type="button" onClick={() => { clearMarkerRef.current = logs.at(-1)?.message ?? ""; setLogs([]); }}>로그지우기</button><button type="button" onClick={() => { clearMarkerRef.current = ""; refreshStored(); }}>새로고침</button></div>
      <div className="source-log-message-slot" role="status">{message && <div className="inline-notice">{message}</div>}</div>
    </article>
    <LogHelpDialog open={logHelpOpen} service={service} source={source} onClose={() => setLogHelpOpen(false)} onOpenManual={onOpenManual} />
  </section>;
}
