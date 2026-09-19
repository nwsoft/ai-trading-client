import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";
import { startSequentialPoll } from "../sequentialPoll";

const ARENA_TABS = ["AI 판단 설명", "전략 판단", "PAPER 점검 결과", "실행·오류 기록"] as const;

function formatRows(rows: unknown[]): string {
  if (!rows.length) return "아직 실행 기록이 없습니다.";
  return rows.slice(-120).map((row) => {
    if (typeof row !== "object" || row == null) return String(row);
    const value = row as Record<string, unknown>;
    const at = String(value.at ?? value.timestamp ?? value.created_at ?? "");
    const type = String(value.type ?? value.event ?? value.kind ?? "기록");
    const payload = value.payload ?? value.message ?? value.reason ?? value.content ?? value.result ?? "";
    const detail = typeof payload === "object" ? JSON.stringify(payload, null, 2) : String(payload);
    return [at, type, detail].filter(Boolean).join(" · ");
  }).join("\n");
}

export function AlphaArenaWorkspace({ client }: { client: GatewayClient }) {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [activeTab, setActiveTab] = useState<(typeof ARENA_TABS)[number]>("AI 판단 설명");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showGuide, setShowGuide] = useState(true);
  const load = () => client.alphaArena().then((next) => { setData(next); setError(""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "AlphaArena 상태 조회 실패"));
  useEffect(() => startSequentialPoll(load, 5000), [client]);
  async function control(action: "start" | "stop") {
    if (action === "start" && !window.confirm("Binance 전용 PAPER 판단 실험을 시작할까요? 전용 DeepSeek 호출 비용이 발생합니다. 실주문과 가상 체결/PnL 검증은 수행하지 않습니다.")) return;
    setBusy(true); setError("");
    try { const response = await client.alphaArenaCommand(action, false); setData(response.result ?? response); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "AlphaArena 명령 실패"); }
    finally { setBusy(false); }
  }
  const events = Array.isArray(data?.events) ? data.events : [];
  const filtered = useMemo(() => events.filter((event: Record<string, unknown>) => {
    const token = String(event?.type ?? event?.event ?? event?.kind ?? "").toLowerCase();
    if (activeTab === "AI 판단 설명") return token.includes("chat") || token.includes("model") || token.includes("prompt");
    if (activeTab === "전략 판단") return token.includes("decision") || token.includes("signal");
    if (activeTab === "PAPER 점검 결과") return token === "paper_result";
    return token.includes("order") || token.includes("exchange") || token.includes("response") || token.includes("error") || token === "lifecycle";
  }), [activeTab, events]);
  const emptyCopy = `${activeTab}: 아직 기록이 없습니다.`;
  return <section className="data-workspace legacy-alpha-arena">
    {showGuide && <div className="modal-backdrop alpha-guide-backdrop" role="presentation">
      <section className="alpha-guide-modal" role="dialog" aria-modal="true" aria-labelledby="alpha-guide-title">
        <h2 id="alpha-guide-title">Alpha Arena 모드 안내</h2>
        <p>AlphaArena는 기본 OFF인 숙련자용 Binance USDT 선물 독립 실험 모드입니다.</p>
        <p>시장 데이터와 직전 결과 → DeepSeek V4 Flash 판단 → 구조화 파서 → AlphaArena 자체 게이트 → PAPER 결과 기록 순서로 동작합니다.</p>
        <strong>기본 가드레일</strong>
        <ul><li>60초 판단 주기(최소 30초), BTC/ETH/SOL/XRP/DOGE/BNB</li><li>레버리지 10~20배 제한, 진입마다 TP와 SL 필수</li><li>심볼 쿨다운 30초, 최대 동시 포지션 6개</li><li>틱당 모델 제시 위험 합계 상한 1,500 USDT</li></ul>
        <p>표준 자동매매의 수익성·포트폴리오·전략 합의 계층과 기존 TP/SL 보험·워치독을 공유하지 않습니다. 실주문은 차단됩니다. PAPER 결과는 AI 판단·조건 점검 기록이며 가상 체결·손익·여권 검증 결과가 아닙니다. 수익률 검증은 전략 스튜디오를 이용하세요. 화면 이동 후에도 실행은 계속되며 상단 상태에서 정지할 수 있습니다.</p>
        <button className="primary-button" type="button" onClick={() => setShowGuide(false)}>확인</button>
      </section>
    </div>}
    <article className="panel arena-control-panel"><h2>AlphaArena · Binance 전용</h2><div className="arena-engine-control"><span>엔진: {String(data?.engine || "확인 중")}</span><b>PAPER 판단 실험 · 실주문 차단</b><button className={data?.running ? "danger-button" : "success-button"} type="button" disabled={busy || (!data?.running && (!data?.available || data?.paper_trading === false))} onClick={() => void control(data?.running ? "stop" : "start")}>{data?.running ? "■정지" : "▶시작"}</button></div></article>
    <p className="inline-notice">가상 체결·청산·PnL은 계산하지 않습니다. 설정 변경 시 실험은 정지하며, 저장한 설정으로 다시 시작해야 합니다. 다른 거래소·증권사 탭은 이 실험의 대상 선택이 아닙니다.</p>
    {data?.paper_trading === false && <div className="inline-notice error-text">현재 앱 설정은 LIVE입니다. AlphaArena는 PAPER에서만 시작할 수 있습니다.</div>}
    {error && <div className="inline-notice error-text">{error}</div>}
    {!data?.available && <div className="inline-notice">설정 → AlphaArena에서 기능을 활성화하고 전용 DeepSeek 키를 저장·점검하세요. Binance 연결과 PAPER 설정도 필요합니다.</div>}
    <article className="panel arena-tab-panel"><nav className="intelligence-tabs" aria-label="AlphaArena 기록">{ARENA_TABS.map((name) => <button key={name} className={activeTab === name ? "active" : ""} type="button" onClick={() => setActiveTab(name)}>{name}</button>)}</nav><pre className="legacy-intelligence-output arena-output">{filtered.length ? formatRows(filtered) : emptyCopy}</pre></article>
    <details className="panel arena-guide"><summary>Alpha Arena 모드 안내</summary><p>AlphaArena는 기본 OFF인 숙련자용 Binance USDT 선물 독립 실험 모드입니다.</p><p>시장 데이터와 직전 결과 → DeepSeek V4 Flash 판단 → 구조화 파서 → AlphaArena 자체 게이트 → PAPER 결과 기록 순서로 동작합니다.</p><p>60초 판단 주기(최소 30초), 레버리지 10~20배 제한, 진입마다 TP·SL 필수, 심볼 쿨다운 30초, 최대 동시 포지션 6개, 틱당 위험 합계 상한 1,500 USDT가 기본 가드레일입니다.</p><p>표준 자율주행의 수익성·포트폴리오·전략 합의 계층과 기존 TP/SL 보험·워치독을 공유하지 않습니다. 실주문은 차단됩니다. PAPER 결과는 AI 판단·조건 점검 기록이며 가상 체결·손익·여권 검증 결과가 아닙니다. 수익률 검증은 전략 스튜디오를 이용하세요. 화면 이동 후에도 실행은 계속되며 상단 상태에서 정지할 수 있습니다.</p></details>
  </section>;
}
