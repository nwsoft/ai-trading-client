import { t } from '../i18n';
import { useEffect, useState, type ReactNode } from "react";

export interface SourceLiveHistory {
  source: string;
  status: string;
  error: string;
  limit: number;
  has_more: boolean;
  records: Array<{
    id: string; source: string; symbol: string; currency: string;
    entry_time: string; exit_time: string; side: string;
    entry_price: number | null; exit_price: number | null; quantity: number | null;
    net_pnl: number | null; evidence: string; strategy_key: string; version_id: string;
  }>;
}

const evidenceLabels: Record<string, string> = {
  confirmed: "체결 대조 완료", unreconciled: "손익 미확정 · 대조 전",
  external: "수동·외부 기록 · 성과 제외", imported: "가져온 기록 · 중복 대조 필요",
};
function amount(value: number | null, currency = "") {
  if (value == null || !Number.isFinite(value)) return "미확정";
  const precision = value !== 0 && Math.abs(value) < 0.000001
    ? { maximumSignificantDigits: 8 }
    : { maximumFractionDigits: currency === "KRW" ? 2 : 8 };
  return `${value.toLocaleString("ko-KR", precision)}${currency ? ` ${currency === "UNKNOWN" ? "통화 미확인" : currency}` : ""}`;
}

export function SourceTradeHistory({ mode, source, history, loading, failed, children }: {
  mode: string; source: string; history?: SourceLiveHistory; loading: boolean; failed: boolean; children: ReactNode;
}) {
  const [tab, setTab] = useState(mode === "paper" ? "paper" : "live");
  const [expanded, setExpanded] = useState(false);
  useEffect(() => { setTab(mode === "paper" ? "paper" : "live"); setExpanded(false); }, [mode, source]);
  const matching = history?.source === source;
  const unavailable = failed || !matching || history?.status !== "available";
  const rows = unavailable ? [] : history?.records ?? [];
  return <section className="source-trade-history" aria-label={t("기관별 거래내역")}>
    <div className="source-history-tabs" role="group" aria-label={t("거래내역 종류")}>
      <button type="button" aria-pressed={tab === "live"} onClick={() => setTab("live")}>{t("LIVE 거래내역")}</button>
      <button type="button" aria-pressed={tab === "paper"} onClick={() => setTab("paper")}>{t("PAPER 검증 이력")}</button>
    </div>
    {tab === "paper" ? loading || failed ? <article className="legacy-exchange-card"><p role="status">{loading ? "PAPER 거래내역 조회 중…" : "PAPER 거래내역을 확인하지 못했습니다. 거래가 없다는 뜻은 아닙니다."}</p></article> : children : <article className="legacy-exchange-card exchange-statistics live-history-card">
      <header className="source-card-header"><div className="source-card-title"><span className="source-card-mark statistics" aria-hidden="true">L</span><div><small>LIVE HISTORY</small><h3>{mode === "live" ? "현재 LIVE 거래내역" : t("과거 LIVE 거래내역")}</h3></div></div><button className="paper-history-toggle" type="button" aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>{expanded ? t("접기") : t("펼치기")}</button></header>
      {mode === "learning" && <p className="spot-holding-scope">{t("LEARNING은 신규 주문을 실행하지 않습니다. 아래는 저장된 과거 기록입니다.")}</p>}
      {mode === "paper" && <p className="spot-holding-scope">{t("현재 PAPER 운용과 분리된 과거 LIVE 기록입니다.")}</p>}
      {expanded && <>
        <p className="spot-holding-scope">{source.toUpperCase()}{t(" · 저장된 LIVE 종료 기록")}{!unavailable ? ` 최근 ${rows.length}건${history?.has_more ? " (이전 기록 더 있음)" : ""}` : ""}{t(". 미체결 주문·진입 중 포지션·거래소 전체 체결 목록과는 다릅니다.")}</p>
        <div className="legacy-paper-history" aria-live="polite">
          {loading ? <div className="empty-state">{t("LIVE 거래내역 조회 중…")}</div> : unavailable ? <div className="empty-state" role="status">{t("LIVE 거래내역을 확인하지 못했습니다. 거래가 없다는 뜻은 아닙니다. 연결·저장 원장을 확인하고 새로고침하세요.")}</div> : !rows.length ? <div className="empty-state">{t("이 기관에 저장된 LIVE 종료 기록이 없습니다.")}</div> : rows.map((row, index) => <div className="source-live-history-row" key={`${row.id}-${index}`}>
            <div className="source-live-history-summary"><b>{row.symbol}</b><span>{row.side || "방향 미기록"}{t(" · 종료")}</span><strong className={row.net_pnl == null ? "" : row.net_pnl < 0 ? "negative" : "positive"}>{row.evidence === "confirmed" ? amount(row.net_pnl, row.currency) : "손익 미확정"}</strong></div>
            <small>{row.exit_time} · {evidenceLabels[row.evidence] ?? "대조 전"}</small>
            <details><summary>{t("거래 근거")}</summary><div>{t("진입 ")}{row.entry_time || "미기록"}<br />{t("진입가 ")}{amount(row.entry_price, row.currency)}{t(" → 청산가 ")}{amount(row.exit_price, row.currency)}{t(" · 수량 ")}{amount(row.quantity)}<br />{row.strategy_key && row.version_id ? `전략 스튜디오 · ${row.strategy_key} · ${row.version_id}` : "전략 귀속 미기록"}</div></details>
          </div>)}
        </div>
      </>}
    </article>}
  </section>;
}
