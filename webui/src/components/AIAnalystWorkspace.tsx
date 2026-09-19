import { t } from '../i18n';
import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";
import type { WorkspaceSnapshot } from "../types";

type AnalysisKind = "portfolio" | "signals" | "risk" | "advice" | "performance" | "news";

const ANALYSIS_CARDS: Array<{
  kind: AnalysisKind;
  title: string;
  eyebrow: string;
  tone: string;
  lines: string[];
  action: string;
  prompt: string;
}> = [
  { kind: "portfolio", eyebrow: "PORTFOLIO", tone: "blue", title: "포트폴리오 종합 분석", lines: ["보유 종목·코인별 수익률 요약", "위험 자산 비중 및 분산 점수", "리밸런싱 필요 여부 판단"], action: "분석 요청", prompt: "현재 포트폴리오를 종합 분석해줘. 위험 분산 수준, 수익률, 리밸런싱 필요 여부를 알려줘." },
  { kind: "signals", eyebrow: "MARKET SIGNAL", tone: "cyan", title: "시장 신호 & 매매 타이밍", lines: ["기술적 지표 기반 매수/매도 신호", "과매수·과매도 구간 감지", "단기·중기 추세 전환점 예측"], action: "신호 확인", prompt: "현재 보유 자산의 매수/매도 신호를 분석해줘. 기술적 지표와 추세 기준으로 설명해줘." },
  { kind: "risk", eyebrow: "RISK GUARD", tone: "red", title: "리스크 평가 & 경고", lines: ["포지션별 최대 손실 시나리오", "집중 위험 자산 알림", "변동성 급등 구간 자동 경보"], action: "리스크 점검", prompt: "현재 포지션의 리스크를 평가해줘. 집중 위험 자산과 최대 손실 시나리오를 알려줘." },
  { kind: "advice", eyebrow: "AI ADVICE", tone: "purple", title: "AI 맞춤 투자 조언", lines: ["현재 투자 성향 진단", "목표 수익률 달성 전략 제안", "설정 최적화 권고사항"], action: "조언 요청", prompt: "내 투자 성향과 현재 상황을 분석해서 맞춤 투자 조언을 해줘. 설정 최적화 방안도 포함해줘." },
  { kind: "performance", eyebrow: "PERFORMANCE", tone: "green", title: "성과 분석 & 비교", lines: ["전략별 누적 수익률 비교", "샤프·소르티노 지수 계산", "최대 낙폭(MDD) 분석"], action: "성과 보기", prompt: "지금까지의 투자 성과를 분석해줘. 누적 수익률, 샤프 지수, 최대 낙폭을 계산해줘." },
  { kind: "news", eyebrow: "NEWS & SENTIMENT", tone: "amber", title: "뉴스 & 감성 분석", lines: ["주요 종목·코인 관련 뉴스 요약", "시장 감성 지수(Sentiment Score)", "이벤트 캘린더 (실적·공시·이슈)"], action: "뉴스 분석", prompt: "현재 보유 자산 관련 주요 뉴스와 시장 감성을 분석해줘. 확인되지 않은 내용은 만들지 말고 출처와 기준시각을 표시해줘." },
];

function pnlText(snapshot: WorkspaceSnapshot | null) {
  const paper = snapshot?.trading?.execution_mode === "paper";
  if (Number(paper ? snapshot?.trading?.closed_count : snapshot?.trading?.reconciled_closed_count) <= 0) return paper ? "청산 기록 없음" : "대조 전";
  const pnl = snapshot?.trading?.pnl_by_currency ?? {};
  const usdt = Number(pnl.USDT ?? 0);
  const krw = Number(pnl.KRW ?? 0);
  const values: string[] = [];
  if (usdt || !krw) values.push(`${usdt >= 0 ? "+" : ""}${usdt.toLocaleString(undefined, { maximumFractionDigits: 4 })} USDT`);
  if (krw) values.push(`${krw >= 0 ? "+" : ""}${krw.toLocaleString()}원`);
  return values.join(" · ");
}

export function AIAnalystWorkspace({
  client,
  onOpenAssistant,
  onOpenSummary,
  onOpenScenario,
}: {
  client: GatewayClient;
  onOpenAssistant: (question?: string) => void;
  onOpenSummary: () => void;
  onOpenScenario: () => void;
}) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [result, setResult] = useState("위의 분석 카드 버튼을 클릭하면 AI가 현재 거래 상황을 분석하여 결과를 표시합니다.\n\n팁: AI 어시스턴트 탭에서 음성으로 분석을 요청할 수도 있습니다.");
  const [error, setError] = useState("");
  const [statisticsMode, setStatisticsMode] = useState<"live" | "paper">("paper");

  const refresh = () => client.workspace("ai_analyst", "ai_analyst.workspace", "", { statisticsMode, statisticsPeriod: "all" })
    .then((next) => { setSnapshot(next); setError(""); })
    .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "AI 애널리스트 데이터를 불러오지 못했습니다."));

  useEffect(() => { void refresh(); }, [client, statisticsMode]);

  const summaryPreview = useMemo(() => {
    const trading = snapshot?.trading;
    const paper = trading?.execution_mode === "paper";
    const reconciledCount = Number(paper ? trading?.closed_count : trading?.reconciled_closed_count) || 0;
    return [
      `종료 거래 ${Number(trading?.closed_count ?? 0).toLocaleString()}건`,
      paper ? `PAPER 가상 청산 ${reconciledCount.toLocaleString()}건 · LIVE 체결과 별도` : `체결 대조 완료 ${reconciledCount.toLocaleString()}건 · 미확정 ${Number(trading?.unresolved_closed_count ?? 0).toLocaleString()}건`,
      `${paper ? "가상 청산" : "확정"} 승률 ${reconciledCount > 0 ? `${Number(trading?.win_rate ?? 0).toFixed(1)}%` : paper ? "청산 기록 없음" : "대조 전"}`,
      `${paper ? "가상" : "확정"} 순손익 ${pnlText(snapshot)}`,
      `저장된 AI 판단 ${snapshot?.ai_decisions?.length ?? 0}건 · 분석 ${snapshot?.ai_analysis?.length ?? 0}건`,
    ].join("\n");
  }, [snapshot]);

  const scenarioPreview = useMemo(() => {
    const risks = snapshot?.risk ?? [];
    if (!risks.length) return "저장된 위험 기록이 없습니다. 표본이 없는 상태를 안전으로 해석하지 않습니다.";
    return `저장된 위험 기록 ${risks.length}건\n최근 기록을 시나리오 점검 탭에서 확인하세요.`;
  }, [snapshot]);

  function requestAnalysis(kind: AnalysisKind, prompt: string) {
    setError("");
    setResult(`${ANALYSIS_CARDS.find((card) => card.kind === kind)?.title ?? "AI 분석"} 요청을 AI 어시스턴트로 전달했습니다.\n\n분석 실행 전 설명 수준과 외부 AI 비용 여부를 확인한 뒤 전송하세요.`);
    onOpenAssistant(prompt);
  }

  const trading = snapshot?.trading;
  const paper = trading?.execution_mode === "paper";
  const reconciledCount = Number(paper ? trading?.closed_count : trading?.reconciled_closed_count) || 0;
  const riskGuard = (snapshot?.risk?.length ?? 0) > 0 ? "경고 확인" : "기록 없음";
  return <section className="analyst-workspace legacy-analyst-workspace">
    <article className="panel analyst-hero">
      <div><h1>{t("AI 통합 애널리스트")}</h1><p>{t("보유 자산·현재 포지션·시장 지표를 종합하여 AI가 맞춤 투자 분석을 제공합니다.")}</p></div>
      <button className="secondary-button" type="button" onClick={refresh}>{t("새로고침")}</button>
    </article>
    {error && <div className="inline-notice error-text">{error}</div>}
    <label>{t("성과 기준 · 전체 기간 ")}<select aria-label={t("애널리스트 성과 모드")} value={statisticsMode} onChange={(event) => setStatisticsMode(event.target.value as "live" | "paper")}><option value="paper">{t("PAPER 가상 원장")}</option><option value="live">{t("LIVE 체결 대조 원장")}</option></select></label>
    <div className="analyst-metrics metric-grid">
      <div className="tone-blue"><span>{t("종료 거래")}</span><strong>{Number(trading?.closed_count ?? 0).toLocaleString()}{t("건")}</strong></div>
      <div className="tone-green"><span>{paper ? t("가상 청산") : t("체결 대조 완료")}{t(" 승률")}</span><strong>{reconciledCount > 0 ? `${Number(trading?.win_rate ?? 0).toFixed(1)}%` : paper ? "청산 기록 없음" : "대조 전"}</strong></div>
      <div className="tone-purple"><span>{paper ? t("가상") : "확정"}{t(" 순손익")}</span><strong>{pnlText(snapshot)}</strong></div>
      <div className="tone-amber"><span>{t("리스크 가드")}</span><strong>{riskGuard}</strong></div>
    </div>
    <article className="panel analyst-jump-row">
      <h2>{t("빠른 이동")}</h2>
      <div className="command-row">
        <button className="secondary-button" type="button" onClick={onOpenSummary}>{t("AI 요약 리포트 탭 열기")}</button>
        <button className="secondary-button" type="button" onClick={onOpenScenario}>{t("시나리오 점검 탭 열기")}</button>
        <button className="primary-button" type="button" onClick={() => onOpenAssistant()}>{t("AI 어시스턴트 열기")}</button>
      </div>
    </article>
    <div className="analyst-card-grid">
      {ANALYSIS_CARDS.map((card) => <article className={`panel analyst-card tone-${card.tone}`} key={card.kind}>
        <span className="analyst-card-eyebrow">{card.eyebrow}</span><h2>{card.title}</h2>
        {card.lines.map((line) => <p key={line}>• {line}</p>)}
        <button className="primary-button" type="button" onClick={() => requestAnalysis(card.kind, card.prompt)}>{card.action}</button>
      </article>)}
    </div>
    <div className="analyst-preview-grid">
      <article className="panel tone-cyan"><span className="analyst-card-eyebrow">EVIDENCE SUMMARY</span><h2>{t("AI 요약 리포트 미리보기")}</h2><div className="analyst-preview-lines">{summaryPreview.split("\n").map((line) => <p key={line}>{line}</p>)}</div></article>
      <article className="panel tone-red"><span className="analyst-card-eyebrow">SCENARIO CHECK</span><h2>{t("시나리오 점검 미리보기")}</h2><div className="analyst-preview-lines">{scenarioPreview.split("\n").map((line) => <p key={line}>{line}</p>)}</div></article>
    </div>
    <div className="command-row analyst-preview-actions"><button className="secondary-button" type="button" onClick={refresh}>{t("미리보기 새로고침")}</button></div>
    <article className="panel analyst-result"><span className="analyst-card-eyebrow">ASSISTANT HANDOFF</span><h2>{t("AI 분석 결과")}</h2><div className="analyst-result-copy">{result.split("\n").filter(Boolean).map((line) => <p key={line}>{line}</p>)}</div></article>
  </section>;
}
