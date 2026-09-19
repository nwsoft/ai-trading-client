import { t } from '../i18n';
import { useEffect, useState } from "react";

import type { GatewayClient } from "../api";
import type { WorkspaceSnapshot } from "../types";
import { LiveHistoryEvidence } from "./LiveHistoryEvidence";

const FILTERS = [
  ["all", "전체"],
  ["crypto", "코인"],
  ["stock", "주식"],
] as const;

function numberText(value: unknown) {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function AIAnalystScenarioWorkspace({ client }: { client: GatewayClient }) {
  const [snapshot, setSnapshot] = useState<WorkspaceSnapshot | null>(null);
  const [filter, setFilter] = useState<(typeof FILTERS)[number][0]>("all");
  const [error, setError] = useState("");
  const [currency, setCurrency] = useState("");
  const [mode, setMode] = useState<"live" | "paper">("live");
  const refresh = () => client.workspace("ai_analyst", "ai_analyst.scenario", "", { statisticsMode: mode, statisticsCurrency: currency })
    .then((next) => { setSnapshot(next); setError(""); })
    .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "시나리오 데이터를 불러오지 못했습니다."));

  useEffect(() => { void refresh(); }, [client, mode, currency]);
  const scenario = snapshot?.scenario;
  const scope = scenario?.scopes?.[filter];
  const policy = scenario?.policy;

  return <section className="scenario-workspace">
    <article className="panel scenario-hero">
      <div><span className="eyebrow">{t("주문 없는 사전 점검")}</span><h1>{t("자동매매 시나리오 점검")}</h1><p>{t("선택 원장의 과거 순손익에 0.7·1.0·1.3 배율을 적용합니다. 전략 진입 조건을 다시 실행한 백테스트가 아닙니다.")}</p><small>{t("이 결과는 과거 기록을 재계산한 추정치이며 주문을 제출하거나 설정을 바꾸지 않습니다.")}</small></div>
      <button className="secondary-button" type="button" onClick={refresh}>{t("새로고침")}</button>
    </article>
    {error && <div className="inline-notice error-text">{error}</div>}
    <article className="panel scenario-basis">
      <div><h2>{t("계산 기준")}</h2><p>{t("LIVE와 PAPER를 분리하고 선택한 자산군의 종료 거래만 사용합니다. 아래 주식 설정은 참고용이며 손익 배율 계산에 진입 임계값을 적용하지 않습니다.")}</p></div>
      <label>{t("성과 원장 ")}<select value={mode} onChange={(event) => setMode(event.target.value as "live" | "paper")}><option value="live">{t("LIVE · 대조 완료")}</option><option value="paper">{t("PAPER · 가상 청산")}</option></select></label>
      <label>{t("통화 ")}<select value={currency} onChange={(event) => setCurrency(event.target.value)}><option value="">{t("전체 · 혼합 합산 금지")}</option>{scenario?.available_currencies?.map((item) => <option key={item}>{item}</option>)}</select></label>
      <label className="scenario-filter"><span>{t("데이터 기준")}</span><select value={filter} onChange={(event) => setFilter(event.target.value as (typeof FILTERS)[number][0])}>{FILTERS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select><strong>{FILTERS.find(([value]) => value === filter)?.[1]}{t(" 거래만 계산")}</strong></label>
    </article>
    {filter === "stock" && <article className="panel scenario-policy-panel">
      <div className="scenario-section-title"><div><span className="eyebrow">{t("설정에서 불러온 값")}</span><h2>{t("현재 자동매매 정책")}</h2></div><span>{t("읽기 전용")}</span></div>
      <div className="scenario-policy-grid">
        <div><span>{t("매수 임계값")}</span><strong>{Number(policy?.buy_threshold ?? 0).toFixed(2)}</strong></div>
        <div><span>{t("매도 임계값")}</span><strong>{Number(policy?.sell_threshold ?? 0).toFixed(2)}</strong></div>
        <div><span>{t("점검 주기")}</span><strong>{policy?.interval_minutes ?? 0}{t("분")}</strong></div>
        <div><span>{t("최대 포지션")}</span><strong>{policy?.max_positions ?? 0}{t("개")}</strong></div>
        <div><span>{t("리스크 가드레일")}</span><strong>{policy?.risk_guard_enabled ? "활성화" : "비활성화"}</strong></div>
      </div>
    </article>}
    <article className="panel scenario-results">
      <div className="scenario-section-title"><div><span className="eyebrow">{t("보수 · 기준 · 공격")}</span><h2>{t("과거 손익 민감도 결과")}</h2></div><span>{scope?.sample_count ?? 0}{t("건 표본")}</span></div>
      {scope?.currency_mixed ? <div className="honest-empty-state"><b>{t("서로 다른 통화의 손익은 합산하지 않습니다.")}</b><span>{t("현재 범위에 ")}{(scope.currencies ?? []).join(" · ")}{t(" 기록이 함께 있습니다.")}</span><span>{t("통화 선택에서 KRW 또는 USDT 등 하나를 선택해 확인하세요.")}</span></div> : !scope?.sample_count ? <div className="honest-empty-state"><b>{t("선택 원장·자산군·통화에 계산 가능한 표본이 없습니다.")}</b><span>{t("시나리오 점검은 ")}{filter === "all" ? t("전체") : filter === "crypto" ? t("코인") : t("주식")}{t(" 종료 거래를 기준으로 계산됩니다.")}</span><span>{t("과거 LIVE 기록이 있어도 체결 대조 전이면 표본에 포함되지 않습니다. 아래 기록 현황과 제외 사유를 확인하세요.")}</span></div> : <>
        <div className="scenario-table scenario-table-header"><span>{t("시나리오")}</span><span>{t("기준 거래수")}</span><span>{t("승률")}</span><span>{t("누적 손익")}</span><span>{t("건당 평균")}</span><span>{t("최대 드로우다운")}</span></div>
        {scope.scenarios.map((row) => <div className="scenario-table" key={String(row.key)} style={{ color: String(row.color ?? "#f9fafb") }}><span><b>{String(row.name)}</b><small>{String(row.description)}</small></span><span>{Number(row.total ?? 0)}{t("건")}</span><span>{Number(row.win_rate ?? 0).toFixed(1)}%</span><span>{Number(row.total_pnl ?? 0) >= 0 ? "+" : ""}{numberText(row.total_pnl)} {String(row.currency ?? "")}</span><span>{Number(row.avg_pnl ?? 0) >= 0 ? "+" : ""}{numberText(row.avg_pnl)} {String(row.currency ?? "")}</span><span>-{numberText(row.max_drawdown)} {String(row.currency ?? "")}</span></div>)}
        <p className="scenario-disclaimer">{t("※ 보수 시나리오는 포지션 비율 70%, 공격 시나리오는 130%를 적용한 과거 거래 기반 추정값입니다. 미래 성과를 보장하지 않으며 주문을 실행하지 않습니다.")}</p>
      </>}
    </article>
    <LiveHistoryEvidence data={scope?.live_history_evidence} />
  </section>;
}
