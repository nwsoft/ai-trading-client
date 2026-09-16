import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";
import { startSequentialPoll } from "../sequentialPoll";

const ARENA_TABS = ["MODEL_CHAT", "TRADING_DECISIONS", "포지션/PnL", "거래소 응답"] as const;

function formatRows(rows: unknown[]): string {
  if (!rows.length) return "아직 실행 기록이 없습니다.";
  return rows.slice(-120).map((row) => {
    if (typeof row !== "object" || row == null) return String(row);
    const value = row as Record<string, unknown>;
    const at = String(value.at ?? value.timestamp ?? value.created_at ?? "");
    const type = String(value.type ?? value.event ?? value.kind ?? "기록");
    const detail = String(value.message ?? value.reason ?? value.content ?? value.result ?? "");
    return [at, type, detail].filter(Boolean).join(" · ");
  }).join("\n");
}

export function AlphaArenaWorkspace({ client }: { client: GatewayClient }) {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [activeTab, setActiveTab] = useState<(typeof ARENA_TABS)[number]>("MODEL_CHAT");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showGuide, setShowGuide] = useState(true);
  const load = () => client.alphaArena().then((next) => { setData(next); setError(""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "AlphaArena 상태 조회 실패"));
  useEffect(() => startSequentialPoll(load, 5000), [client]);
  async function control(action: "start" | "stop") {
    if (action === "start" && !window.confirm("AlphaArena를 시작하시겠습니까? 독립 게이트가 적용되며 현재 운영 모드와 주문 권한을 먼저 확인하세요.")) return;
    setBusy(true); setError("");
    try { const response = await client.alphaArenaCommand(action, false); setData(response.result ?? response); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "AlphaArena 명령 실패"); }
    finally { setBusy(false); }
  }
  const events = Array.isArray(data?.events) ? data.events : [];
  const filtered = useMemo(() => events.filter((event: Record<string, unknown>) => {
    const token = String(event?.type ?? event?.event ?? event?.kind ?? "").toLowerCase();
    if (activeTab === "MODEL_CHAT") return token.includes("chat") || token.includes("model") || token.includes("prompt");
    if (activeTab === "TRADING_DECISIONS") return token.includes("decision") || token.includes("signal");
    if (activeTab === "포지션/PnL") return token.includes("position") || token.includes("pnl") || token.includes("trade");
    return token.includes("order") || token.includes("exchange") || token.includes("response") || token.includes("error");
  }), [activeTab, events]);
  const emptyCopy = activeTab === "MODEL_CHAT" ? "MODEL_CHAT 기록이 여기에 표시됩니다." : activeTab === "TRADING_DECISIONS" ? "TRADING_DECISIONS가 여기에 표시됩니다." : activeTab === "포지션/PnL" ? "포지션 정보와 PnL 정보가 여기에 표시됩니다." : "거래소 응답이 여기에 표시됩니다.";
  return <section className="data-workspace legacy-alpha-arena">
    {showGuide && <div className="modal-backdrop alpha-guide-backdrop" role="presentation">
      <section className="alpha-guide-modal" role="dialog" aria-modal="true" aria-labelledby="alpha-guide-title">
        <h2 id="alpha-guide-title">Alpha Arena 모드 안내</h2>
        <p>AlphaArena는 기본 OFF인 숙련자용 Binance USDT 선물 독립 실험 모드입니다.</p>
        <p>시장 데이터와 직전 결과 → DeepSeek V4 Flash 판단 → 구조화 파서 → AlphaArena 자체 게이트 → PAPER 결과 기록 순서로 동작합니다.</p>
        <strong>기본 가드레일</strong>
        <ul><li>60초 판단 주기(최소 30초), BTC/ETH/SOL/XRP/DOGE/BNB</li><li>레버리지 10~20배 제한, 진입마다 TP와 SL 필수</li><li>심볼 쿨다운 30초, 최대 동시 포지션 6개</li><li>틱당 모델 제시 위험 합계 상한 1,500 USDT</li></ul>
        <p>표준 자동매매의 수익성·포트폴리오·전략 합의 계층과 기존 TP/SL 보험·워치독을 공유하지 않습니다. v3.9.1.37에서는 LIVE가 차단되며, 처음 사용자는 표준 LEARNING/PAPER와 전략 스튜디오부터 검증하세요.</p>
        <button className="primary-button" type="button" onClick={() => setShowGuide(false)}>확인</button>
      </section>
    </div>}
    <article className="panel arena-control-panel"><h2>AlphaArena</h2><div className="arena-engine-control"><span>엔진:</span><select value="deepseek-v4-flash" disabled><option>deepseek-v4-flash</option></select><small>(Qwen: 다음 버전 예정)</small><button className={data?.running ? "danger-button" : "success-button"} type="button" disabled={busy || !data?.available} onClick={() => void control(data?.running ? "stop" : "start")}>{data?.running ? "■정지" : "▶시작"}</button></div></article>
    {error && <div className="inline-notice error-text">{error}</div>}
    {!data?.available && <div className="inline-notice">설정 → AlphaArena에서 기능을 활성화하고 AI 엔진/API 연결 상태를 확인하세요.</div>}
    <article className="panel arena-tab-panel"><nav className="intelligence-tabs" aria-label="AlphaArena 기록">{ARENA_TABS.map((name) => <button key={name} className={activeTab === name ? "active" : ""} type="button" onClick={() => setActiveTab(name)}>{name}</button>)}</nav><pre className="legacy-intelligence-output arena-output">{filtered.length ? formatRows(filtered) : emptyCopy}</pre></article>
    <details className="panel arena-guide"><summary>Alpha Arena 모드 안내</summary><p>AlphaArena는 기본 OFF인 숙련자용 Binance USDT 선물 독립 실험 모드입니다.</p><p>시장 데이터와 직전 결과 → DeepSeek V4 Flash 판단 → 구조화 파서 → AlphaArena 자체 게이트 → PAPER 결과 기록 순서로 동작합니다.</p><p>60초 판단 주기(최소 30초), 레버리지 10~20배 제한, 진입마다 TP·SL 필수, 심볼 쿨다운 30초, 최대 동시 포지션 6개, 틱당 위험 합계 상한 1,500 USDT가 기본 가드레일입니다.</p><p>표준 자율주행의 수익성·포트폴리오·전략 합의 계층과 기존 TP/SL 보험·워치독을 공유하지 않습니다. v3.9.1.37에서는 LIVE가 차단되며, 처음 사용자는 표준 LEARNING/PAPER와 전략 스튜디오부터 검증하세요.</p></details>
  </section>;
}
