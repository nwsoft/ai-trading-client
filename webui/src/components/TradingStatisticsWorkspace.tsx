import { t } from '../i18n';
import { useEffect, useRef, useState } from "react";

import type { GatewayClient } from "../api";
import type { RuntimeSnapshot, WorkspaceSnapshot } from "../types";
import { RecordRecoveryPanel } from './RecordRecoveryPanel';
import { ExecutionEvidenceNote, executionEvidenceCount } from './ExecutionEvidenceNote';

type StatisticsPeriod = "today" | "7d" | "30d" | "all" | "custom";

function numberText(value: unknown, digits = 2) {
  const number = Number(value ?? 0);
  return Number.isFinite(number)
    ? number.toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits })
    : "—";
}

function optionalNumberText(value: unknown, digits = 2) {
  return value === null || value === undefined || value === "" ? "—" : numberText(value, digits);
}

function currencyText(values: Record<string, number> | undefined, digits = 2) {
  const rows = Object.entries(values ?? {}).filter(([, value]) => Number.isFinite(Number(value)));
  if (!rows.length) return numberText(0, digits);
  return rows.map(([currency, value]) => `${numberText(value, currency === "KRW" ? 0 : digits)} ${currency}`).join(" · ");
}

function holdText(value: unknown) {
  const minutes = Number(value);
  if (!Number.isFinite(minutes) || minutes <= 0) return "수집 대기";
  if (minutes < 60) return `${numberText(minutes, 1)}분`;
  return `${numberText(minutes / 60, 1)}시간`;
}

function executionCountText(count: number, status: string | undefined) {
  return executionEvidenceCount(count,status);
}

export function TradingStatisticsWorkspace({
  client,
  runtime,
  service,
  sources,
  defaultSource,
}: {
  client: GatewayClient;
  runtime: RuntimeSnapshot | null;
  service: "blockchain" | "stock";
  sources: string[];
  defaultSource?: string;
}) {
  const [selectedSource, setSelectedSource] = useState("all");
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [period, setPeriod] = useState<StatisticsPeriod>("today");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const initialMode = defaultSource && String(runtime?.execution_modes?.[defaultSource] ?? "").toLowerCase() === "paper" ? "paper" : "live";
  const [statisticsMode, setStatisticsMode] = useState<"live" | "paper">(initialMode);
  const requestSequence = useRef(0);

  function refresh() {
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError("");
    if (period === "custom" && !customStart) {
      setLoading(false);
      setError("사용자 지정 시작일을 선택하세요.");
      return;
    }
    client.workspace(service, `${service}.statistics`, selectedSource === "all" ? "" : selectedSource, {
      statisticsPeriod: period,
      statisticsStart: customStart,
      statisticsEnd: customEnd,
      statisticsMode,
    })
      .then((next) => { if (requestId === requestSequence.current) setSnapshot(next); })
      .catch((reason: unknown) => { if (requestId === requestSequence.current) setError(reason instanceof Error ? reason.message : "거래 통계를 불러오지 못했습니다."); })
      .finally(() => { if (requestId === requestSequence.current) setLoading(false); });
  }

  async function importTrades() {
    const targets = selectedSource === "all" ? [...sources] : [selectedSource];
    if (!targets.length) {
      setError("동기화할 거래소가 없습니다. 설정에서 거래소를 먼저 활성화하세요.");
      return;
    }
    setLoading(true); setError(""); setMessage(`${targets.map((source) => source.toUpperCase()).join(" · ")} 실제 체결을 동기화하는 중입니다...`);
    try {
      const summaries: string[] = [];
      const failures: string[] = [];
      for (const source of targets) {
        try {
          const response = await client.runtimeCommand("trades.import", source);
          const result = (response.result ?? {}) as Record<string, any>;
          summaries.push(`${source.toUpperCase()} 확인 ${Number(result.received ?? 0)} · 신규 ${Number(result.inserted ?? 0)} · 기존 ${Number(result.skipped ?? 0)}`);
        } catch (reason) {
          failures.push(`${source.toUpperCase()}: ${reason instanceof Error ? reason.message : "동기화 실패"}`);
        }
      }
      setMessage(`${summaries.join(" | ")}${failures.length ? ` | 실패 ${failures.join(" / ")}` : ""}`);
      if (failures.length === targets.length) setError("선택한 거래소의 체결 동기화가 모두 실패했습니다.");
      refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "거래소 체결 동기화에 실패했습니다.");
      setMessage(""); setLoading(false);
    }
  }

  useEffect(() => { refresh(); }, [client, service, selectedSource, period, customStart, customEnd, statisticsMode]);
  useEffect(() => {
    if (selectedSource !== "all" && !sources.includes(selectedSource)) setSelectedSource("all");
  }, [selectedSource, sources]);

  const statistics = snapshot?.trading_statistics ?? snapshot?.period_statistics;
  const groups = statistics?.groups ?? [];
  const filterLabel = service === "stock" ? "증권사 필터" : "거래소 필터";
  const reconciledCount = Number(statistics?.reconciled_closed_count ?? 0);
  const isPaper = statistics?.execution_mode === "paper";
  const performanceCount = isPaper ? Number(statistics?.closed_count ?? 0) : reconciledCount;
  const performanceLabel = isPaper ? "가상 청산" : "체결 대조 완료";
  const unresolvedCount = Number(statistics?.unresolved_closed_count ?? 0);
  const exchangeReference = statistics?.exchange_pnl_reference;
  const emptyPerformance = isPaper ? "청산 기록 없음" : "대조 전";
  const totalPnl = performanceCount > 0 ? currencyText(statistics?.pnl_by_currency) : emptyPerformance;
  const totalFees = currencyText(statistics?.fees_by_currency);
  const feeEntries = Object.entries(statistics?.fees_by_currency ?? {}).filter(([, value]) => Number.isFinite(Number(value)));
  const footerFee = feeEntries.length === 1 ? numberText(feeEntries[0][1]) : totalFees;
  const sourceLabel = selectedSource === "all" ? "전체" : selectedSource.toUpperCase();
  const range = statistics?.range;
  const rangeLabel = range?.started_at
    ? `${new Date(String(range.started_at)).toLocaleString()} ~ ${new Date(String(range.ended_at)).toLocaleString()} (로컬 시간)`
    : `최초 기록 ~ ${range?.ended_at ? new Date(String(range.ended_at)).toLocaleString() : "현재"} (로컬 시간)`;

  async function updateBaseline(action: "set" | "clear") {
    const source = selectedSource === "all" ? "" : selectedSource;
    const scopedLabel = selectedSource === "all"
      ? (service === "stock" ? "전체 증권사" : "전체 거래소")
      : `${sourceLabel} ${service === "stock" ? "증권사" : "거래소"}`;
    if (action === "set") {
      const warning = `${scopedLabel} LIVE 통계의 표시 기준을 지금으로 새로 시작할까요?\n\n선택한 표시 범위만 바뀝니다. 이전 거래·체결·학습·전략 PAPER·위험 기록은 삭제되지 않습니다. 열린 포지션과 가드레일에도 영향이 없습니다. 이후 청산된 거래부터 기본 통계에 계산됩니다.`;
      if (!window.confirm(warning)) return;
    }
    setLoading(true); setError(""); setMessage("");
    try {
      const state = await client.updateStatisticsBaseline(service, source, action);
      setMessage(action === "set"
        ? `표시 기준을 ${new Date(String(state.baseline_at)).toLocaleString()}부터 새로 시작했습니다. 원본 기록은 보존됩니다.`
        : "표시 기준을 해제했습니다. 보관된 전체 기록을 다시 계산합니다.");
      refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "통계 표시 기준을 변경하지 못했습니다.");
      setLoading(false);
    }
  }

  const baselineActive = Boolean(snapshot?.statistics_view?.active);
  const periodButtons: Array<[StatisticsPeriod, string]> = [
    ["today", "오늘"], ["7d", "7일"], ["30d", "30일"], ["all", "전체"], ["custom", "사용자 지정"],
  ];
  const periodControls = <div className="legacy-stat-period-controls" aria-label={t("통계 범위")}>
    <div className="legacy-stat-period-buttons" aria-label={t("실행 모드")}><button type="button" className={statisticsMode === "live" ? "active" : ""} onClick={() => setStatisticsMode("live")}>LIVE</button><button type="button" className={statisticsMode === "paper" ? "active" : ""} onClick={() => setStatisticsMode("paper")}>PAPER</button></div>
    <div className="legacy-stat-period-buttons">{periodButtons.map(([value, label]) => <button type="button" className={period === value ? "active" : ""} key={value} onClick={() => setPeriod(value)}>{label}</button>)}</div>
    {period === "custom" && <div className="legacy-stat-custom-range"><label>{t("시작일")}<input type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} /></label><label>{t("종료일")}<input type="date" value={customEnd} min={customStart || undefined} onChange={(event) => setCustomEnd(event.target.value)} /></label></div>}
    <div className="legacy-stat-baseline-actions">
      {statisticsMode === "live" && <button type="button" onClick={() => void updateBaseline("set")} disabled={loading}>{t("통계 표시 기준 새로 시작")}</button>}
      {statisticsMode === "live" && baselineActive && <button type="button" onClick={() => void updateBaseline("clear")} disabled={loading}>{t("전체 기록 복원")}</button>}
      <span>{statisticsMode === "paper" ? "PAPER 가상 원장 · LIVE 및 표시 기준과 분리" : baselineActive ? `기준 적용: ${new Date(String(snapshot?.statistics_view?.baseline_at)).toLocaleString()}` : "원본 전체 기록 보존"}</span>
    </div>
  </div>;

  return <section className="legacy-trading-statistics">
    <header className="legacy-stat-filter">
      <h1>{t("거래 통계 · ")}{statisticsMode.toUpperCase()} ({statisticsMode === "paper" ? "가상 원장" : "데이터베이스"}{t(" 기준)")}</h1>
      <label>{filterLabel}
        <select value={selectedSource} onChange={(event) => setSelectedSource(event.target.value)}>
          <option value="all">{t("전체")}</option>
          {sources.map((source) => <option key={source} value={source}>{source.toUpperCase()}</option>)}
        </select>
      </label>
    </header>
    {periodControls}
    <p className="workspace-copy">{t("조회 범위: ")}{rangeLabel} · {sourceLabel} · {statisticsMode.toUpperCase()}{t(". 전체 대시보드는 오늘, 기관별 카드는 전체 기간입니다. 같은 기간·기관·모드로 비교하세요.")}</p>
    {statisticsMode === "live" && <aside className="workspace-copy" aria-label={t("손익 비교 기준")}>
      <p><b>{t("NoahAI 연결 청산 순손익")}{unresolvedCount > 0 ? " · 확정분 부분 합계" : ""}: {totalPnl}</b>{t(" · 진입·청산 수수료 반영 기준, 펀딩비 포함 계좌 총손익과는 다릅니다.")}</p>
      <p>{t("거래소 수집 체결 실현손익 · 비용 차감 전: ")}{Number(exchangeReference?.pnl_present_count ?? 0) > 0 ? currencyText(exchangeReference?.gross_pnl_by_currency) : "제공값 없음 / 확인 전"}{t(" · 손익값 없는 체결 ")}{Number(exchangeReference?.pnl_missing_count ?? 0)}{t("건")}</p>
      <p>{t("수집 체결은 수동 거래를 포함할 수 있습니다. 거래소 계좌 전체·누적 PnL은 아직 대조되지 않았으며 수수료·세금·펀딩비·조회 기간·진입 원가 기준을 맞춰야 비교할 수 있습니다. 표시 기준 초기화는 원장과 학습 기록을 삭제하지 않습니다.")}</p>
      {unresolvedCount > 0 && <p role="alert"><b>{t("미확정 ")}{unresolvedCount}{t("건이 있어 전체 손익·승률은 아직 확정할 수 없습니다. 아래 숫자는 대조 완료분만의 부분 합계입니다.")}</b></p>}
    </aside>}
    <div className={`legacy-stat-feedback${error ? " error-text" : ""}`} role="status" aria-live="polite">
      {error || message || (Number(statistics?.legacy_unattributed_count ?? 0) > 0
        ? `레거시 출처 미확정 ${Number(statistics?.legacy_unattributed_count).toLocaleString()}건은 보존되며 기관별 합계에서 제외됩니다.`
        : `조회 범위: ${rangeLabel}`)}
    </div>
    <div className="legacy-stat-kpis">
      <article className="trades"><span>{statisticsMode === "paper" ? t("가상 청산") : "NoahAI 청산"}</span><strong>{Number(statistics?.closed_count ?? 0).toLocaleString()}{t("건")}</strong></article>
      <article className="win-rate"><span>{performanceLabel}{t(" 승률")}</span><strong>{performanceCount > 0 ? `${numberText(statistics?.win_rate, 1)}%` : emptyPerformance}</strong></article>
      <article className="pnl"><span>{performanceLabel}{t(" 순손익")}{!isPaper && unresolvedCount > 0 ? " · 부분 합계" : ""}</span><strong>{totalPnl}</strong></article>
      <article className="fees"><span>{t("기간 Fee")}</span><strong>{totalFees}</strong></article>
    </div>
    <div className="legacy-stat-operating"><b>{statisticsMode === "paper" ? "모의 운용" : "실제 운용"}</b><span>{statisticsMode === "paper" ? `가상 청산 ${Number(statistics?.closed_count ?? 0).toLocaleString()}건` : `${service === "stock" ? "증권사" : "거래소"} 확인 체결 ${executionCountText(Number(statistics?.execution_count ?? 0), statistics?.execution_history_status)}`} | {statisticsMode === "paper" ? "가상 " : ""}{t("체결금액 ")}{currencyText(statistics?.notional_by_currency)}{t(" | 평균 보유시간 ")}{holdText(statistics?.avg_hold_minutes)}{t(" (유효 ")}{statistics?.valid_hold_count ?? 0}/{statistics?.closed_count ?? 0}{t("건)")}</span></div>
    {statisticsMode === 'live' && <ExecutionEvidenceNote status={statistics?.execution_history_status} rows={statistics?.execution_rows ?? []} count={Number(statistics?.execution_count ?? 0)} />}
    <div className="legacy-stat-table">
      <div className="legacy-stat-header">
        {[service === "stock" ? "종목" : "코인", "총 거래", "익절", "손절", "승률", "평균 순수익률", "연결 청산 총손익", "순손익", "수수료·세금", "최대 순수익", "최대 순손실"].map((label) => <b key={label}>{label}</b>)}
      </div>
      <div className="legacy-stat-body">
      {groups.map((group) => <section className="legacy-stat-group" key={String(group.source)}>
        <h2>{String(group.label)}{group.attribution_status === "legacy_source_unconfirmed" ? " · 출처 미확정" : ""}</h2>
        <p>{t("총 ")}{Number(group.closed_count ?? 0).toLocaleString()}{t("건 | ")}{performanceLabel}{t(" 순손익 ")}{Number(isPaper ? group.closed_count : group.reconciled_count) > 0 ? `${numberText(group.total_pnl)} ${String(group.currency ?? "")}` : emptyPerformance}{t(" | 비용 ")}{numberText(group.total_fees)} {String(group.currency ?? "")} | {isPaper ? "가상 원장 기준 · 거래소 체결 대조 대상 아님" : `체결 대조 ${Number(group.reconciled_count ?? 0)}/${Number(group.closed_count ?? 0)}건 · 미확정 ${Number(group.unresolved_count ?? 0)}건`}</p>
        <p className="operating">{isPaper ? t("가상") : "실제"}{t(" 체결금액 ")}{numberText(group.total_notional)} {String(group.currency ?? "")}{t(" | 평균 보유시간 ")}{holdText(group.avg_hold_minutes)}{t(" (유효 ")}{Number(group.valid_hold_count ?? 0)}/{Number(group.closed_count ?? 0)}{t("건)")}</p>
        {(group.rows ?? []).map((row: Record<string, any>) => <div className="legacy-stat-row" key={`${String(group.source)}-${String(row.symbol)}`}>
          <b>{String(row.symbol ?? "—")}</b>
          <span title={`체결 대조 ${Number(row.reconciled_count ?? 0)}/${Number(row.total_trades ?? 0)}건`}>{Number(row.total_trades ?? 0)}</span><span>{Number(row.winning_trades ?? 0)}</span><span>{Number(row.losing_trades ?? 0)}</span>
          <strong className={Number(row.win_rate) >= 50 ? "positive" : Number(row.win_rate) > 0 ? "negative" : ""}>{row.win_rate == null ? "—" : `${numberText(row.win_rate, 1)}%`}</strong>
          <strong className={Number(row.avg_profit_rate) > 0 ? "positive" : Number(row.avg_profit_rate) < 0 ? "negative" : ""}>{row.avg_profit_rate == null ? "—" : `${numberText(row.avg_profit_rate)}%`}</strong>
          <span title={row.reconciliation_status === "unresolved" ? "대조 미확정" : String(row.reconciliation_status ?? "")}>{optionalNumberText(row.gross_pnl)}</span>
          <span title={row.reconciliation_status === "confirmed" ? "체결 대조 완료 순손익" : "대조 완료된 거래만 합산"}>{row.total_pnl == null ? "—" : `${Number(row.total_pnl) >= 0 ? "+" : ""}${numberText(row.total_pnl)}`}</span><span>{numberText(row.total_fees)}</span><span>{optionalNumberText(row.max_profit)}</span><span>{optionalNumberText(row.max_loss)}</span>
        </div>)}
      </section>)}
      {!loading && !groups.length && <div className="empty-state">{sourceLabel}{t(" 기준으로 청산된 거래가 없습니다.")}</div>}
      {loading && <div className="empty-state">{t("거래 통계를 불러오는 중입니다.")}</div>}
      </div>
    </div>
    <footer>
      <button type="button" onClick={refresh} disabled={loading}>{t("화면 다시 계산")}</button>
      {service === "blockchain" && statisticsMode === "live" && <button type="button" onClick={importTrades} disabled={loading}>{t("거래소 체결 동기화")}</button>}
      <span>{selectedSource === "all" ? `전체 ${service === "stock" ? "증권사" : "거래소"}` : `${sourceLabel} ${service === "stock" ? "증권사" : "거래소"}`}{t(" 기준 ")}{statisticsMode.toUpperCase()}{t(" 통계를 갱신했습니다. (청산 종목 ")}{groups.reduce((sum, group) => sum + Number((group.rows ?? []).length), 0)}{t("개, ")}{statisticsMode === "paper" ? `가상 청산 ${Number(statistics?.closed_count ?? 0)}건` : `거래소 확인 체결 ${executionCountText(Number(statistics?.execution_count ?? 0), statistics?.execution_history_status)}, NoahAI 청산 ${Number(statistics?.closed_count ?? 0)}건 · 대조 완료 ${Number(statistics?.reconciled_closed_count ?? 0)}건 · 미확정 ${Number(statistics?.unresolved_closed_count ?? 0)}건`}{t(", 누적 Fee ")}{footerFee}{selectedSource === "all" ? " 각 기관 기준통화" : ` ${feeEntries[0]?.[0] ?? "기준통화"}`})</span>
    </footer>
    {statisticsMode === 'live' && <details><summary>{t('거래 기록 점검·복구')}</summary>
      <RecordRecoveryPanel client={client} sources={sources} initialSource={selectedSource === 'all' ? defaultSource : selectedSource} />
    </details>}
  </section>;
}
