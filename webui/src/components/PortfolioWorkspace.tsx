import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";
import { LiveHistoryEvidence } from "./LiveHistoryEvidence";

type Row = Record<string, any>;

const LEGACY_PORTFOLIO_SECTION_ORDER = ["통합 자산 현황", "자산군별 비중", "리스크 요약", "추천 액션"] as const;

function format(value: unknown, digits = 2) {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: digits });
}

function currencyAmount(value: unknown, currency: string) {
  return currency === "KRW" ? `${format(value, 0)}원` : `${format(value, 4)} ${currency}`;
}

function concentrationLabel(row: Row | undefined) {
  const value = String(row?.concentration ?? "");
  if (value === "high") return "높음";
  if (value === "medium") return "중간";
  if (value === "balanced") return "낮음";
  return "데이터 없음";
}

function concentrationScore(row: Row | undefined) {
  return Math.max(Number(row?.max_weight ?? 0) * 100, Number(row?.hhi ?? 0) * 100);
}

function LegacyOverviewSections({
  allocations,
  performances,
  correlation,
  mode,
}: {
  allocations: Array<[string, Row]>;
  performances: Array<[string, Row]>;
  correlation: Row;
  mode: "live" | "paper";
}) {
  const maxConcentration = Math.max(0, ...allocations.map(([, row]) => concentrationScore(row)));
  const pnl = performances.length
    ? performances.map(([currency, row]) => currencyAmount(row.net_pnl, currency)).join(" · ")
    : "선택 원장의 계산 가능한 표본 없음";
  return <>
    <article className="panel portfolio-section legacy-portfolio-summary">
      <div className="panel-heading"><div><h2>{LEGACY_PORTFOLIO_SECTION_ORDER[1]}</h2></div></div>
      {allocations.length ? <div className="legacy-portfolio-allocation-list">{allocations.map(([currency, row]) => <div key={currency}>
        <strong>{currency}</strong>
        <span>{currencyAmount(row.total_value, currency)}</span>
        <span>최대 단일 비중 {format(Number(row.max_weight) * 100)}%</span>
        <span className={`state-pill ${row.concentration === "balanced" ? "ok" : "warn"}`}>집중도 {concentrationLabel(row)}</span>
      </div>)}</div> : <div className="honest-empty-state"><b>현재 계좌 잔고가 아직 수신되지 않았습니다.</b><span>블록체인 또는 주식/증권 계좌의 API를 연결한 뒤 실시간 계좌 새로고침을 실행하세요.</span></div>}
    </article>
    <article className="panel portfolio-section legacy-portfolio-summary">
      <div className="panel-heading"><div><h2>{LEGACY_PORTFOLIO_SECTION_ORDER[2]}</h2></div></div>
      <div className="legacy-portfolio-risk-list">
        <div><span>집중도</span><strong>{allocations.length ? `${format(maxConcentration, 0)}/100` : "N/A"}</strong></div>
        <div><span>자산군 상관계수</span><strong>{correlation?.status === "ok" ? Number(correlation.value ?? 0).toFixed(2) : "N/A"}</strong></div>
        <div><span>{mode === "paper" ? "PAPER 가상 순손익" : "LIVE 체결 대조 완료 순손익"}</span><strong>{pnl}</strong></div>
      </div>
      <small className="workspace-copy">상세 손실 시나리오와 대응 방향은 ‘리스크 브리핑’ 탭에서 확인합니다.</small>
    </article>
    <article className="panel portfolio-section legacy-portfolio-summary">
      <div className="panel-heading"><div><h2>{LEGACY_PORTFOLIO_SECTION_ORDER[3]}</h2></div><span className="state-pill ok">판단 보조 전용</span></div>
      <p className="portfolio-guidance">{allocations.length ? "집중도가 높은 통화군의 단일 자산 비중부터 점검하고, 자산 배분 진단에서 리밸런싱 근거를 확인하세요." : "계좌 데이터를 새로고침한 뒤 자산 배분 진단을 실행하세요. 이 안내는 주문을 만들거나 실행하지 않습니다."}</p>
      <small className="workspace-copy">사용자의 승인 없이 주문 설정을 바꾸거나 거래를 실행하지 않습니다.</small>
    </article>
  </>;
}

function AllocationSections({ allocations, correlation }: { allocations: Array<[string, Row]>; correlation: Row }) {
  return <>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>{LEGACY_PORTFOLIO_SECTION_ORDER[1]}</h2></div></div>
      {allocations.length ? <div className="card-grid">{allocations.map(([currency, row]) => <section className="insight-card" key={currency}>
        <header><strong>{currency}</strong><span className={`state-pill ${row.concentration === "balanced" ? "ok" : "warn"}`}>집중도 {concentrationLabel(row)}</span></header>
        <dl><dt>평가 합계</dt><dd>{currencyAmount(row.total_value, currency)}</dd><dt>최대 단일 비중</dt><dd>{format(Number(row.max_weight) * 100)}%</dd><dt>HHI</dt><dd>{format(row.hhi, 4)}</dd></dl>
        <div className="weight-list">{Object.entries(row.weights ?? {}).map(([symbol, weight]) => <div key={symbol}><span>{symbol}</span><progress max={1} value={Number(weight)} /><strong>{format(Number(weight) * 100)}%</strong></div>)}</div>
      </section>)}</div> : <div className="honest-empty-state"><b>현재 계좌 잔고가 아직 수신되지 않았습니다.</b><span>블록체인 또는 주식/증권 계좌의 API를 연결한 뒤 실시간 계좌 새로고침을 실행하세요.</span></div>}
    </article>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>포트폴리오 집중도 (HHI)</h2></div></div>
      {allocations.length ? <div className="portfolio-hhi-list">{allocations.map(([currency, row]) => <div key={currency}><div><strong>{currency}</strong><span>집중도 {format(concentrationScore(row), 1)}/100 ({concentrationLabel(row)})</span></div><progress max={100} value={concentrationScore(row)} /></div>)}</div> : <div className="empty-state">비중을 계산할 계좌 데이터가 없습니다.</div>}
    </article>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>자산군 상관계수 히트맵</h2></div></div>
      {correlation?.status === "ok" ? <div className="correlation-grid"><span>암호화폐</span><b>+1.00</b><b>{Number(correlation.value ?? 0).toFixed(2)}</b><span>주식</span><b>{Number(correlation.value ?? 0).toFixed(2)}</b><b>+1.00</b></div> : <div className="honest-empty-state"><b>표본 데이터 부족</b><span>암호화폐와 주식의 같은 날짜 수익률이 충분히 쌓이면 자동 계산됩니다.</span></div>}
    </article>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>리밸런싱 제안</h2></div></div>
      {!allocations.length ? <div className="empty-state">계좌 데이터를 확인한 뒤 제안을 계산합니다.</div> : allocations.map(([currency, row]) => <p className="portfolio-guidance" key={currency}><strong>{currency}</strong> · {String(row.guidance ?? "현재 통화군 내 비중을 유지 관찰하세요.")}</p>)}
      <p className="workspace-copy">제안은 정보 제공용이며 주문으로 자동 적용되지 않습니다. KRW와 USDT는 환율 기준시각 없이 합산하지 않습니다.</p>
    </article>
  </>;
}

function RiskSections({ allocations, performances, correlation }: { allocations: Array<[string, Row]>; performances: Array<[string, Row]>; correlation: Row }) {
  const maxConcentration = Math.max(0, ...allocations.map(([, row]) => concentrationScore(row)));
  const concentration = maxConcentration >= 60 ? "높음" : maxConcentration >= 45 ? "중간" : allocations.length ? "낮음" : "데이터 없음";
  const correlationText = correlation?.status === "ok" ? Number(correlation.value ?? 0).toFixed(2) : "N/A";
  const pnlRows = performances.map(([currency, row]) => [currency, Number(row.net_pnl ?? 0)] as const);
  const warnings = [
    !allocations.length ? "편중 위험 미판정: 현재 계좌 잔고가 아직 수신되지 않았습니다." : maxConcentration >= 60 ? "편중 위험 높음: 단일 자산 의존도가 높아 급변동 구간 방어력이 약합니다." : maxConcentration >= 45 ? "편중 위험 중간: 비중 변화가 커지는 자산을 주간 단위로 점검하세요." : "편중 위험 낮음: 현재 통화군 내 분산 구조는 비교적 안정적입니다.",
    correlation?.status === "ok" ? `연동 위험 점검: 상관계수 ${correlationText}` : "연동 위험 미판정: 같은 날짜의 자산군 시계열 표본이 부족합니다.",
  ];
  return <>
    <div className="portfolio-risk-cards">
      <section><span>집중도</span><strong>{maxConcentration ? `${format(maxConcentration, 0)}/100` : "N/A"}</strong><small>{concentration}</small></section>
      <section><span>상관계수</span><strong>{correlationText}</strong><small>{correlation?.status === "ok" ? "계산 완료" : "데이터 없음"}</small></section>
      <section><span>실현 손익</span><strong>{pnlRows.length ? pnlRows.map(([currency, pnl]) => currencyAmount(pnl, currency)).join(" · ") : "N/A"}</strong><small>가져오기 거래 제외</small></section>
    </div>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>시나리오별 손실액 추정</h2></div></div>
      {!allocations.length ? <div className="honest-empty-state"><b>현재 잔고가 수신되지 않아 손실액을 계산하지 않습니다.</b><span>통화가 다른 자산은 환율 없이 하나의 손실액으로 합산하지 않습니다.</span></div> : <div className="portfolio-scenario-table">
        <div><b>통화</b><b>하락 -5%</b><b>하락 -10%</b><b>하락 -20%</b><b>하락 -30%</b><b>하락 -50%</b></div>
        {allocations.map(([currency, row]) => <div key={currency}><strong>{currency}</strong>{[.05, .1, .2, .3, .5].map((rate) => <span key={rate}>-{currencyAmount(Number(row.total_value ?? 0) * rate, currency)}</span>)}</div>)}
      </div>}
    </article>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>리스크 경고 및 대응 방향</h2></div></div>
      <div className="portfolio-warning-list">{warnings.map((warning) => <p className={warning.includes("높음") ? "danger" : ""} key={warning}>• {warning}</p>)}</div>
      <strong className="portfolio-action-title">즉시 권장 액션</strong>
      <p className="portfolio-guidance">→ 계좌 데이터의 기준시각과 통화를 확인하고, 집중도가 높은 통화군의 단일 자산 비중부터 점검하세요.</p>
    </article>
  </>;
}

function PerformanceSections({ performances, recentTrades }: { performances: Array<[string, Row]>; recentTrades: Row[] }) {
  return <>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>성과·위험 요약</h2></div></div>
      {performances.length ? <div className="card-grid">{performances.map(([currency, row]) => <section className="insight-card" key={currency}><header><strong>{currency}</strong><span>{Number(row.trades ?? 0)}거래</span></header><dl><dt>순손익</dt><dd>{currencyAmount(row.net_pnl, currency)}</dd><dt>승률</dt><dd>{format(Number(row.win_rate) * 100)}%</dd><dt>Profit Factor</dt><dd>{row.profit_factor == null ? "손실 표본 없음" : format(row.profit_factor)}</dd><dt>최대 누적 손실폭</dt><dd>{currencyAmount(row.max_drawdown_amount, currency)}</dd></dl></section>)}</div> : <div className="honest-empty-state"><b>선택 원장의 계산 가능한 종료 거래 표본이 없습니다.</b><span>거래 이력이나 성과 자체가 없다는 뜻은 아닙니다. 과거 LIVE 기록과 대조 상태를 아래에서 확인하세요.</span></div>}
    </article>
    <article className="panel portfolio-section">
      <div className="panel-heading"><div><h2>최근 종료 거래</h2></div><span className="count-badge">{recentTrades.length}건</span></div>
      {recentTrades.length ? <div className="portfolio-recent-trades"><div><b>종목</b><b>자산군</b><b>손익</b><b>종료 시각</b></div>{recentTrades.slice(0, 30).map((row, index) => <div key={`${row.symbol}-${row.exit_time}-${index}`}><strong>{String(row.symbol ?? "-")}</strong><span>{String(row.asset_type ?? row.asset_class ?? "-")}</span><span>{currencyAmount(row.pnl, String(row.currency ?? "USDT"))}</span><span>{String(row.exit_time ?? row.timestamp ?? "-")}</span></div>)}</div> : <div className="empty-state">표시할 종료 거래가 없습니다.</div>}
    </article>
  </>;
}

export function PortfolioWorkspace({ client, featureId, enabledSources, credentialStatus }: { client: GatewayClient; featureId: string; enabledSources: string[]; credentialStatus: Record<string, boolean> }) {
  const [data, setData] = useState<Row | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"live" | "paper">("live");
  const load = () => client.portfolioAnalysis(mode).then((next) => { setData(next); setError(""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "포트폴리오 분석 조회 실패"));
  useEffect(() => { void load(); }, [client, featureId, mode]);
  async function refreshAccounts() {
    if (!enabledSources.length) { setError("설정에서 거래소 또는 증권사 연결 범위를 먼저 선택하세요."); return; }
    const configuredSources = enabledSources.filter((source) => credentialStatus[source]);
    if (!configuredSources.length) { setError("설정에서 거래소 또는 증권사 API 키를 먼저 등록한 뒤 연결을 확인하세요."); return; }
    setBusy(true); setError("");
    try { await client.refreshAccounts(configuredSources, true); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "계좌 새로고침 실패"); }
    finally { setBusy(false); }
  }
  async function saveSnapshot() {
    setBusy(true); setError("");
    try { await client.savePortfolioSnapshot(); await load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "자산 스냅샷 저장 실패"); }
    finally { setBusy(false); }
  }
  const allocations = useMemo(() => Object.entries(data?.allocation_by_currency ?? {}) as Array<[string, Row]>, [data]);
  const performances = useMemo(() => Object.entries(data?.performance_by_currency ?? {}) as Array<[string, Row]>, [data]);
  const saved = data?.saved_snapshot ?? {};
  const title = featureId.endsWith("allocation") ? "자산 배분 진단" : featureId.endsWith("risk") ? "리스크 브리핑" : featureId.endsWith("performance") ? "성과·위험 분석" : "자산 통합 인사이트";
  const totalByCurrency = Object.fromEntries(allocations.map(([currency, row]) => [currency, Number(row.total_value ?? 0)]));
  const currentAssetText = Object.keys(totalByCurrency).length
    ? `현재 자산(통화별): ${Object.entries(totalByCurrency).map(([currency, value]) => currencyAmount(value, currency)).join(" · ")} | 환율 없이 통합 합계 미계산`
    : "현재 잔고 미수신 | 블록체인 또는 주식/증권 계좌에서 잔고를 먼저 조회하세요.";
  const snapshotText = saved.saved_at
    ? `마지막 저장: ${String(saved.saved_at)}${saved.currency_totals && typeof saved.currency_totals === "object" ? ` | ${Object.entries(saved.currency_totals as Record<string, number>).map(([currency, value]) => currencyAmount(value, currency)).join(" · ")}` : ""}`
    : "저장된 자산 스냅샷이 없습니다.";
  return <section className="data-workspace portfolio-workspace">
    <article className="panel portfolio-hero"><div className="panel-heading"><div><h1>{title}</h1><p>실제 계좌 잔고와 종료 거래 기록을 분리해 계산합니다. 통화가 다른 자산은 환율 근거 없이 합산하지 않습니다.</p></div><button className="secondary-button" type="button" disabled={busy} onClick={refreshAccounts}>{busy ? "처리 중…" : "실시간 계좌 새로고침"}</button></div>{error && <div className="inline-notice error-text">{error}</div>}</article>
    <article className="panel portfolio-mode-panel"><label>성과 원장 <select value={mode} onChange={(event) => setMode(event.target.value as "live" | "paper")}><option value="live">LIVE · 체결 대조 완료</option><option value="paper">PAPER · 가상 청산</option></select></label><p>{data?.performance_basis}</p><p>자산 배분은 실제 잔고 기준이며 PAPER 성과를 실제 잔고에 더하지 않습니다.</p><p>{data?.allocation_basis}</p>{Number(data?.unvalued_position_count ?? 0) > 0 && <p className="error-text">가격 미확인 보유 {data?.unvalued_position_count}건은 평가에서 제외했습니다. 현재 비중은 부분 평가이며 전체 계좌 위험을 뜻하지 않습니다.</p>}{Object.entries(data?.account_status ?? {}).map(([source, value]) => <small key={source}>{source.toUpperCase()} · {String((value as Row).status)} · {String((value as Row).captured_at ?? "기준 시각 없음")}　</small>)}</article>
    <LiveHistoryEvidence data={data?.live_history_evidence} />
    {featureId.endsWith("insights") && <>
      <p className="workspace-copy">{data?.performance_basis}</p>
      <article className="panel portfolio-section legacy-portfolio-summary">
        <h2>{LEGACY_PORTFOLIO_SECTION_ORDER[0]}</h2>
        <p className="legacy-portfolio-status-line">{currentAssetText}</p>
        <div className="legacy-portfolio-snapshot-row">
          <span>{snapshotText}</span>
          <button className="primary-button" type="button" disabled={busy} onClick={saveSnapshot}>현재 상태 저장</button>
        </div>
      </article>
      <LegacyOverviewSections mode={mode} allocations={allocations} performances={performances} correlation={data?.correlation ?? {}} />
    </>}
    {featureId.endsWith("allocation") && <AllocationSections allocations={allocations} correlation={data?.correlation ?? {}} />}
    {featureId.endsWith("risk") && <RiskSections allocations={allocations} performances={performances} correlation={data?.correlation ?? {}} />}
    {featureId.endsWith("performance") && <PerformanceSections performances={performances} recentTrades={Array.isArray(data?.recent_closed_trades) ? data.recent_closed_trades : []} />}
  </section>;
}
