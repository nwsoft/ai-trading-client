import { strategyDifficultyLabel } from '../strategyDifficulty';
import { t } from '../i18n';
import { useEffect, useMemo, useRef, useState } from "react";

import type { GatewayClient } from "../api";
import type { StrategyCatalog, StrategyVersion } from "../types";
import { venueProfile, venueProfilesForService } from "../venueSources";
import { StrategyReplayChart } from "./StrategyReplayChart";
import { strategyExplanationPrompt } from "../strategyExplanation";
import { StrategyBeginnerExplanation, StrategyBeginnerHelp } from "./StrategyBeginnerExplanation";

const STRATEGY_HUB_URL = "https://daltrading.net/strategies";
const STRATEGY_HUB_GUIDE_URL = `${STRATEGY_HUB_URL}/guide`;
const STRATEGY_HUB_SUBMIT_URL = `${STRATEGY_HUB_URL}/submit`;
const STRATEGY_HUB_LIBRARY_URL = `${STRATEGY_HUB_URL}/library`;

const MARKET_REGIME_OPTIONS = [
  { value: "all", label: "잘 모르겠어요 · NoahAI가 판단 (권장)", shortLabel: "NoahAI 판단" },
  { value: "bull", label: "상승장", shortLabel: "상승장" },
  { value: "bear", label: "하락장", shortLabel: "하락장" },
  { value: "range", label: "횡보장", shortLabel: "횡보장" },
  { value: "volatile", label: "고변동성", shortLabel: "고변동성" },
  { value: "calm", label: "저변동성", shortLabel: "저변동성" },
] as const;

const MARKET_REGIME_VALUES = new Set(MARKET_REGIME_OPTIONS.map((item) => item.value));

function normalizeMarketRegimes(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : [value];
  const normalized = raw.map((item) => String(item ?? "").trim().toLowerCase()).filter((item) => MARKET_REGIME_VALUES.has(item as any));
  const unique = [...new Set(normalized)];
  return !unique.length || unique.includes("all") ? ["all"] : unique;
}

function marketRegimeLabels(regimes: string[]): string[] {
  return regimes.map((value) => MARKET_REGIME_OPTIONS.find((item) => item.value === value)?.shortLabel ?? value);
}

const STARTER_RULES = {
  entry: "RSI 30 이하 LONG",
  exit: "RSI 55 이상 청산",
  stop_loss: "1%",
  take_profit: "2%",
  position_size: "5%",
  market_conditions: ["NoahAI 판단"],
  market_regimes: ["all"],
  target_scope: "exchange:binance",
  signal_mode: "independent",
  entry_signal: "LONG",
  exit_policy: { mode: "strategy_owned" },
  executable_entry: { all: [{ field: "rsi", operator: "lte", value: 30 }] },
  executable_exit: { all: [{ field: "rsi", operator: "gte", value: 55 }] },
  engine_settings: { _unit: "percent_points", tp_percent: 2, sl_percent: 1 },
};

const BEGINNER_PRESETS = [
  { key: "auto_regime", label: "AI가 시장에 맞춰 자동 대응", name: "NoahAI 시장 국면 자동 대응", source: "NoahAI 기본 판단이 시장 국면을 먼저 확인하고 추세·눌림목·횡보·돌파 중 조건이 맞는 방식만 검토합니다. 조건이 충돌하거나 맞는 전략이 없으면 HOLD합니다." },
  { key: "trend_follow", label: "추세 따라가기", name: "추세 따라가기", source: "EMA 20·50·200 정렬과 가격·RSI·거래량을 확인해 명확한 추세 방향만 따릅니다. 횡보장과 고변동성에서는 신규 진입하지 않습니다." },
  { key: "trend_pullback", label: "눌림목 진입", name: "눌림목 진입", source: "EMA50·EMA200으로 큰 추세를 확인한 뒤 EMA20·EMA50 부근 조정이 끝나고 거래량이 회복될 때만 추세 방향으로 재진입합니다." },
  { key: "range_rsi", label: "횡보장 저점·고점 대응", name: "횡보장 저점·고점 대응", source: "평평한 추세와 박스권이 확인된 경우에만 RSI 반전을 사용하고 추세 또는 거래량 돌파가 시작되면 즉시 중지합니다." },
  { key: "volume_breakout", label: "강한 거래량 돌파", name: "강한 거래량 돌파", source: "가격 범위가 축소된 뒤 거래량을 동반한 20봉 고점·저점 돌파만 검토합니다. 이미 과도한 고변동성이면 HOLD합니다." },
] as const;

const SAFE_USE_STEPS = [
  "설정 → AI 엔진/API에서 Provider·API 키·모델을 확인합니다.",
  "전략 스튜디오 전략을 실제 자동매매 엔진에서 사용을 ON으로 저장합니다.",
  "AI 멘토 인터뷰 또는 직접 자료 입력으로 시작합니다.",
  "처음에는 기본 AI 후보 확인(권장)을 선택합니다.",
  "Level 1·2·3에서 원문 근거·지원 상태·적용값·누락 조건을 확인합니다. 전문가는 Level 4에서 운용 정책을 선택합니다.",
  "다중 시간봉 규칙을 썼다면 규칙 안전성 검사를 통과합니다.",
  "검토한 전략을 새 버전으로 저장합니다.",
  "사용자가 저장 버전을 직접 승인합니다.",
  "자체 진입조건 전략은 비용 포함 과거 시세 재생 검사를 확인하고, NoahAI 기본 진입 보조 전략은 과거재생 비대상을 확인합니다.",
  "PAPER 전진검증을 시작해 실주문 없이 새 근거를 모읍니다.",
  "최소 3건·7일의 PAPER 결과를 확인한 뒤 사용자가 검증 버전을 최종 적용합니다.",
  "실계정 권한·가드레일·소액 E2E 확인 후에만 LIVE를 사용합니다.",
] as const;

const LEVEL_GUIDE = [
  {
    level: 1,
    profile: "초보자 · 처음 전략을 가져오는 사용자",
    canDo: "자료 범위·요약·원문 근거·누락·위험을 쉬운 문장으로 확인하고, NoahAI 판단 + 기본 AI 후보 확인으로 시작합니다.",
    scenario: "이동평균 아이디어나 영상 설명만 있다면 먼저 의미와 빠진 조건을 확인하고, 자동 저장·승인 없이 초안을 검토합니다.",
  },
  {
    level: 2,
    profile: "일반 · 규칙과 적용값을 확인하려는 사용자",
    canDo: "진입·청산·TP/SL·시장국면·거래소 범위와 기본 위험정책을 확인하고 버전 저장, 승인, 자동검증, PAPER로 진행합니다.",
    scenario: "TradingView/Pine 전략을 가져와 실제 엔진에 전달될 핵심값과 미지원 조건을 확인한 뒤 PAPER 결과를 쌓습니다.",
  },
  {
    level: 3,
    profile: "고급 · 전략을 직접 설계·수정해 온 사용자",
    canDo: "원문-규칙 추적, 전체 Noah Strategy IR, 안전 선언형 규칙 JSON과 독립 후보·국면 범위를 검토·편집합니다.",
    scenario: "상승·하락·횡보 규칙을 전략별로 분리하고 우선순위·포함 범위·다중 시간대 조건을 근거와 함께 관리합니다.",
  },
  {
    level: 4,
    profile: "전문가·실험실 · 운용 정책까지 비교하려는 사용자",
    canDo: "Level 3 전체 기능에 안정형·표준형·적극형 운용 정책과 위험예산·최대 비중·레버리지·동시 포지션 요청·국면 이탈 대응을 더합니다. 계좌 마스터 상한 안에서만 실행됩니다.",
    scenario: "같은 승인 전략을 계정 위험에 맞는 운용 정책으로 비교하되, LIVE 승인·손실 중단·주문 규격·TP/SL·긴급 중지는 해제하지 못합니다.",
  },
] as const;

const RISK_POLICY_PRESETS = {
  conservative: { label: "안정형", riskPerTrade: "0.25", maxMargin: "5", leverageCap: "1", maxPositions: "1", conflictFallback: "커스텀 신규 진입 일시정지" },
  standard: { label: "표준형", riskPerTrade: "0.5", maxMargin: "10", leverageCap: "3", maxPositions: "3", conflictFallback: "기본 노아AI에 맡김" },
  active: { label: "적극형", riskPerTrade: "1.0", maxMargin: "20", leverageCap: "5", maxPositions: "5", conflictFallback: "기본 노아AI에 맡김" },
} as const;

const MENTOR_FIELDS = [
  { key: "asset_class", label: "운용 자산", options: [["crypto", "암호화폐"], ["stock", "주식·ETF"], ["both", "둘 다"]] },
  { key: "capital_band", label: "운용 규모", options: [["small", "소규모"], ["medium", "중간"], ["large", "대규모"]] },
  { key: "review_frequency", label: "확인 주기", options: [["intraday", "장중 수시"], ["daily", "하루 1회"], ["weekly", "주 1회"]] },
  { key: "trade_frequency", label: "선호 거래 빈도", options: [["low", "낮음"], ["medium", "보통"], ["high", "높음"]] },
  { key: "leverage_allowed", label: "레버리지", options: [["false", "사용 안 함"], ["true", "사용 가능"]] },
  { key: "experience_level", label: "전략 경험", options: [["beginner", "초보"], ["intermediate", "일반"], ["advanced", "고급"]] },
  { key: "paper_ready", label: "PAPER 검증", options: [["true", "먼저 진행"], ["false", "아직 어려움"]] },
] as const;

const GUIDED_STEP_LABELS = ["시작 방법", "쉬운 질문", "설명 확인", "버전 만들기", "PAPER 시작"] as const;

type GuidedStartMethod = "" | "noah" | "example" | "import";

type StrategyAuthoringMode = "source_faithful" | "guided_clarification" | "noah_delegate";

export type StrategyAssistantDraft = { id: number; service: "blockchain" | "stock"; text: string };

const AUTHORING_MODES: Array<{ value: StrategyAuthoringMode; label: string; description: string }> = [
  {
    value: "source_faithful",
    label: "원문 그대로 구조화",
    description: "원문에서 확인되지 않은 진입·청산·수치를 만들지 않습니다. 모호하거나 빠진 조건은 실행을 차단합니다.",
  },
  {
    value: "guided_clarification",
    label: "질문으로 함께 완성",
    description: "누락 조건을 한 번에 하나씩 질문합니다. 사용자가 직접 확정한 답변만 별도 근거로 추가하고 다시 분석합니다.",
  },
  {
    value: "noah_delegate",
    label: "기본 NoahAI에 맡기기",
    description: "커스텀 진입 규칙을 만들지 않습니다. NoahAI 기본 후보·시장판단·위험관리 경로를 사용합니다.",
  },
];

const GUIDED_METHOD_COPY: Record<Exclude<GuidedStartMethod, "">, { title: string; description: string }> = {
  noah: {
    title: "기본 NoahAI에 맡기기",
    description: "시장국면·후보·방향·위험은 NoahAI가 판단합니다. 별도 커스텀 전략을 만들 필요 없이 기본 운용 확인으로 끝납니다.",
  },
  example: {
    title: "예제 전략으로 따라하기",
    description: "앱에 포함된 관리형 선언 규칙으로 시작합니다. 외부 AI API를 호출하지 않고 실행 조건과 위험을 확인한 뒤 PAPER까지 연습합니다.",
  },
  import: {
    title: "내 전략 가져오기",
    description: "자연어·Pine Script·문서·이미지·영상·TradingView 자료를 가져와 원문 근거와 실제 실행 규칙이 같은지 확인합니다.",
  },
};

const levelView = (level: number) => level >= 4 ? "Level 4 전문가 운용" : level >= 3 ? "Level 3 전체 근거" : level === 2 ? "Level 2 핵심값" : "Level 1 이해·시험";

function actionLabel(version: StrategyVersion) {
  if (version.active) return "적용 해제";
  if (version.paper_observing || version.status === "paper_observing") return "PAPER 일시정지";
  if (version.status === "paper_paused") return "PAPER 검증 재개";
  if (version.status === "analyzed") return "사용자 승인";
  if (version.status === "approved") return historicalReplayApplicable(version) ? "과거 시세 재생 검사" : "PAPER 전진검증 시작";
  if (version.status === "execution_rejected") return historicalReplayApplicable(version) ? "과거 시세 재생 다시 검사" : "PAPER 전진검증 시작";
  if (version.status === "execution_validated" && version.execution_validation?.mode === "historical_replay") return "PAPER 전진검증 시작";
  if (version.status === "paper_validated") return "전략 적용";
  if (version.status === "execution_validated" && ["live_observation", "limited_live"].includes(String(version.execution_validation?.mode ?? ""))) return "전략 적용";
  return "";
}

function historicalReplayApplicable(version: StrategyVersion) {
  const readiness = version.execution_readiness ?? version.paper_execution_readiness;
  if (typeof readiness?.historical_validation_applicable === "boolean") {
    return readiness.historical_validation_applicable;
  }
  const subject = readiness?.validation_subject ?? version.validation_subject;
  if (subject === "noah_base_with_custom_risk_exit") return false;
  if (subject === "custom_entry_logic") return true;
  // Preserve the existing validation path for legacy versions whose stored
  // readiness predates the explicit applicability contract.
  return true;
}

function strategyStatusLabel(version: StrategyVersion) {
  if (version.active) return "적용 중";
  if (version.paper_observing || version.status === "paper_observing") return "PAPER 검증 중";
  if (version.status === "paper_paused") return "PAPER 일시정지";
  return version.status;
}

function normalizedSubmitSourceKind(kind: string, reference: string): "text" | "pine" | "document" | "image" | "video" | "url" | "manual" {
  if (["youtube", "tradingview", "url"].includes(kind) || /^https?:\/\//i.test(reference)) return "url";
  if (kind === "pine") return "pine";
  if (kind === "pdf") return "document";
  if (kind === "image") return "image";
  if (kind === "video") return "video";
  if (kind === "text") return "text";
  return "manual";
}

function readableDetail(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "-";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function metricNumber(value: unknown, digits = 2): string {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString("ko-KR", { maximumFractionDigits: digits }) : "-";
}

function defaultExecutionTarget(service: "blockchain" | "stock", selectedSource = ""): string {
  const profile = venueProfile(selectedSource);
  if (profile?.service === service) {
    return `${service === "stock" ? "broker" : "exchange"}:${profile.client_id}`;
  }
  return service === "stock" ? "asset:stock" : "asset:crypto";
}

function executionTargetLabel(service: "blockchain" | "stock", targetScope: string): string {
  if (targetScope === "asset:crypto") return "호환되는 모든 암호화폐 거래소";
  if (targetScope === "asset:stock") return "호환되는 모든 증권사";
  const selected = (targetScope.split(":", 2)[1] || "").split(",").map((id) => venueProfile(id)).filter(Boolean);
  if (selected.length > 1) return selected.map((profile) => profile!.display_name).join(" · ") + " 선택";
  const profile = selected[0];
  return profile ? `${profile.display_name} 전용` : service === "stock" ? "현재 증권사 전용" : "현재 거래소 전용";
}

function venueCompatibilityText(service: "blockchain" | "stock", targetScope: string, selectedSource = ""): string[] {
  const targetId = targetScope.includes(":") ? targetScope.split(":", 2)[1] : selectedSource;
  const targetProfile = venueProfile(targetId);
  if (targetScope.startsWith("broker:") && targetProfile) {
    return [
      `${targetProfile.display_name} · 주식/ETF 현물 · 보유하지 않은 종목의 신규 매도(공매도) 금지`,
      "증권사별 주문 규격·거래시간·최소 수량을 다시 검사하며 레버리지는 1배로 제한",
    ];
  }
  if (targetScope.startsWith("exchange:") && targetProfile) {
    return [
      `${targetProfile.display_name} · ${targetProfile.quote_currency} ${targetProfile.market_type === "futures" ? "선물" : "현물"} · ${targetProfile.can_short ? "LONG/SHORT 지원" : "보유 자산 범위 매수·매도만 지원"}`,
      `${targetProfile.order_amount_unit} 주문 단위 · 최소주문·정밀도·비용·보호 주문 계약을 실행 직전 재검사`,
    ];
  }
  const targetIds = targetId.split(",");
  const compatibleProfiles = venueProfilesForService(service).filter((profile) => profile.paper_supported && (!/^(broker|exchange):/.test(targetScope) || targetIds.includes(profile.id)));
  if (service === "stock") return [
    `${compatibleProfiles.map((profile) => profile.display_name).join("·") || "등록된 증권사 없음"} · 주식·ETF 현물 · 공매도·레버리지를 자동 허용하지 않음`,
    "증권사별 주문 규격·거래시간·최소 수량·수수료·세금과 성과를 각각 분리",
  ];
  const spotNames = compatibleProfiles.filter((profile) => profile.market_type === "spot").map((profile) => profile.display_name).join("·");
  const futuresNames = compatibleProfiles.filter((profile) => profile.market_type === "futures").map((profile) => profile.display_name).join("·");
  return [
    `${spotNames || "등록된 현물 거래소 없음"} · 현물 · 보유 자산 범위 매수·매도만 지원`,
    `${futuresNames || "등록된 선물 거래소 없음"} · 선물 · 기관별 SHORT·레버리지 capability 적용`,
    "같은 전략도 기관별 지원 방향·주문 규격을 통과해야 하며 PAPER/LIVE·기관·통화별 성과를 분리 집계",
  ];
}

function StrategyValidationEvidence({ version }: { version: StrategyVersion }) {
  const lab = version.validation_lab && typeof version.validation_lab === "object" ? version.validation_lab : null;
  const performance = lab?.performance && typeof lab.performance === "object" ? lab.performance as Record<string, any> : null;
  const gate = lab?.minimum_quality_gate && typeof lab.minimum_quality_gate === "object" ? lab.minimum_quality_gate as Record<string, any> : null;
  const overfit = lab?.overfit_risk && typeof lab.overfit_risk === "object" ? lab.overfit_risk as Record<string, any> : null;
  const evidence = Array.isArray(version.paper_evidence_by_venue) ? version.paper_evidence_by_venue : [];
  const compatibility = Array.isArray(version.venue_compatibility) ? version.venue_compatibility : [];
  const subject = String(
    version.validation_subject
      ?? version.execution_readiness?.validation_subject
      ?? version.paper_execution_readiness?.validation_subject
      ?? "source_preserved_not_executable",
  );
  if (!lab && !evidence.length && !compatibility.length) return null;
  const validationMetrics = version.execution_validation?.metrics && typeof version.execution_validation.metrics === "object"
    ? version.execution_validation.metrics as Record<string, any>
    : {};
  const source = String(validationMetrics.validation_source ?? validationMetrics.exchange ?? validationMetrics.broker ?? "기록된 검증 시세").toUpperCase();
  const marketType = String(validationMetrics.market_type ?? validationMetrics.asset_class ?? "").toUpperCase();
  return <details className="strategy-validation-evidence">
    <summary>{t("검증 근거 보기 · ")}{lab ? t("과거 시세 재생") : "PAPER"}{evidence.length ? ` · 기관 ${evidence.length}곳` : ""}</summary>
    <p className={subject === "custom_entry_logic" ? "strategy-evidence-pass" : "strategy-evidence-warning"}>{t("검증 대상: ")}{subject === "custom_entry_logic"
        ? "원문에서 구조화된 사용자 진입·청산 규칙"
        : subject === "noah_base_with_custom_risk_exit"
          ? "NoahAI 기본 진입 + 사용자가 선언한 위험·청산값 (원문 전체 전략 실행 검증 아님)"
          : "원문 보존본 · 아직 실행 규칙이 아니므로 PAPER 성과 검증 불가"}
    </p>
    {lab && <>
      <p className="strategy-evidence-source">{t("과거재생 기준: ")}{source}{marketType ? ` · ${marketType}` : ""}{t(" · 과거 결과는 미래 수익 보장이나 자동 적용 근거가 아닙니다.")}</p>
      <p className="strategy-evidence-source">{t("시간봉 ")}{String(validationMetrics.validation_interval ?? "구버전 미기록")}{t(" · 완성 캔들 ")}{String(validationMetrics.candle_count ?? "미기록")}{t("개")}<br />{String(validationMetrics.range_started_at ?? "시작 시각 미기록")} ~ {String(validationMetrics.range_ended_at ?? "종료 시각 미기록")} (UTC)</p>
      <div className="strategy-validation-metrics">
        <div><span>{t("표본")}</span><b>{metricNumber(lab.sample?.total, 0)}{t("건")}</b></div>
        <div><span>{t("순손익")}</span><b>{metricNumber(performance?.total_net_pnl)}</b></div>
        <div><span>{t("수익률")}</span><b>{metricNumber(performance?.total_return_percent)}%</b></div>
        <div><span>MDD</span><b>{metricNumber(performance?.max_drawdown_percent)}%</b></div>
        <div><span>{t("승률")}</span><b>{metricNumber(Number(performance?.win_rate ?? 0) * 100)}%</b></div>
        <div><span>Profit factor</span><b>{metricNumber(performance?.profit_factor)}</b></div>
        <div><span>{t("OOS 순손익")}</span><b>{metricNumber(lab.out_of_sample_net_pnl)}</b></div>
        <div><span>{t("워크포워드 통과")}</span><b>{metricNumber(Number(lab.walkforward?.pass_rate ?? 0) * 100)}%</b></div>
      </div>
      <p className={gate?.passed === true && overfit?.flagged !== true ? "strategy-evidence-pass" : "strategy-evidence-warning"}>{t("최소 품질 필터 ")}{gate?.passed === true ? "통과" : "미통과"}{t(" · 과최적화 위험 ")}{overfit?.flagged === true ? "감지" : "미감지"}
        {Array.isArray(gate?.reasons) && gate.reasons.length ? ` · 사유: ${gate.reasons.join(", ")}` : ""}
        {Array.isArray(overfit?.reasons) && overfit.reasons.length ? ` · 위험: ${overfit.reasons.join(", ")}` : ""}
      </p>
    </>}
    <StrategyReplayChart version={version} />
    {evidence.length > 0 && <div className="strategy-paper-evidence">
      <h5>{t("거래소별 PAPER 전진검증")}</h5>
      {evidence.map((row) => <div key={`${row.exchange}:${row.quote_currency}`}>
        <b>{row.exchange.toUpperCase()} · {row.quote_currency}</b>
        <span>{t("유효 ")}{row.valid_trades}{t("건 · 승 ")}{row.wins}{t(" / 패 ")}{row.losses}{t(" / 보합 ")}{row.breakeven}{t(" · 승률 ")}{row.win_rate === null ? "미산출" : `${metricNumber(row.win_rate)}%`}{t(" · 순손익 ")}{metricNumber(row.net_pnl)}{t(" · 총비용 ")}{metricNumber(row.total_cost ?? row.fees)}{row.estimated_taxes ? ` (수수료 ${metricNumber(row.fees)} · 세금 ${metricNumber(row.estimated_taxes)} · 슬리피지 ${metricNumber(row.estimated_slippage)})` : ""}{row.estimated_cost_trades ? ` · 추정 비용 ${row.estimated_cost_trades}건` : ""}{row.recovered_cost_trades ? ` (구형 기본계약 복구 ${row.recovered_cost_trades}건)` : ""}{row.cost_policy_issue_trades ? ` · 비용 설정 대체 ${row.cost_policy_issue_trades}건` : ""}{row.unavailable_cost_trades ? ` · 비용 미확정 ${row.unavailable_cost_trades}건` : ""}{row.unverified_trades ? ` · 과거 손익 미확정 ${row.unverified_trades}건` : ""}</span>
      </div>)}
    </div>}
    {compatibility.length > 0 && <div className="strategy-compatibility-evidence">
      <h5>{t("이 버전의 거래소 방향 호환성")}</h5>
      {compatibility.map((row) => <div className={row.status} key={row.venue}>
        <b>{row.venue.toUpperCase()} · {row.market_type.replaceAll("_", " ").toUpperCase()}</b>
        <span>{row.status === "compatible" ? "호환" : row.status === "partial" ? "부분 호환" : t("차단")}{t(" · 요청 ")}{row.requested_directions.join("/")}{t(" · 지원 ")}{row.supported_directions.join("/")} · {row.reason}</span>
      </div>)}
    </div>}
    <p className="strategy-evidence-footnote">{t("과거 재생 통과만으로 LIVE가 허용되지 않습니다. PAPER 전진검증, 사용자 최종 적용, 계정 가드레일을 모두 별도로 통과해야 합니다.")}</p>
  </details>;
}

function StrategyVersionContract({ version }: { version: StrategyVersion }) {
  const rules = version.rules ?? {};
  const engine = rules.engine_settings && typeof rules.engine_settings === "object" ? rules.engine_settings : {};
  const risk = rules.risk_model && typeof rules.risk_model === "object" ? rules.risk_model : {};
  const regimes = normalizeMarketRegimes(rules.market_regimes ?? rules.market_conditions);
  const exitPolicy = typeof rules.exit_policy === "object"
    ? String(rules.exit_policy?.mode ?? "-")
    : String(rules.exit_policy ?? "-");
  return <details className="strategy-version-contract">
    <summary>{t("이 버전에 저장된 실행 파라미터 보기")}</summary>
    <dl>
      <div><dt>{t("시장상황")}</dt><dd>{marketRegimeLabels(regimes).join(" · ")}</dd></div>
      <div><dt>{t("전략 역할")}</dt><dd>{String(rules.signal_mode ?? "-")}</dd></div>
      <div><dt>{t("판단 시간봉")}</dt><dd>{String(rules.decision_timeframe ?? rules.timeframe ?? "구버전 미기록 · 시간봉 확인 후 새 버전 저장")}</dd></div>
      <div><dt>{t("진입 방향")}</dt><dd>{String(rules.entry_signal || "원문 조건")}</dd></div>
      <div><dt>{t("청산 책임")}</dt><dd>{exitPolicy}</dd></div>
      <div><dt>TP / SL</dt><dd>{readableDetail(engine.tp_percent)} / {readableDetail(engine.sl_percent)}</dd></div>
      <div><dt>{t("요청 레버리지")}</dt><dd>{readableDetail(risk.max_leverage ?? engine.leverage)}</dd></div>
      <div><dt>{t("거래당 위험")}</dt><dd>{readableDetail(risk.risk_per_trade_percent)}</dd></div>
      <div><dt>{t("동시 포지션 요청")}</dt><dd>{readableDetail(risk.max_concurrent_positions)}</dd></div>
      <div><dt>{t("적용 범위")}</dt><dd>{readableDetail(rules.target_scope)}</dd></div>
      <div><dt>{t("IR 해시")}</dt><dd>{version.ir_hash || "기록 없음"}</dd></div>
    </dl>
    <small>{t("이 값은 해당 버전의 저장 계약입니다. 실제 주문값은 계좌 상한·시장·성과·거래소 규격에 따라 같거나 더 작아질 수 있으며 검증 거래 내보내기에서 실제 적용값을 확인합니다.")}</small>
  </details>;
}

const READINESS_REASON_LABELS: Record<string, string> = {
  document_conditions_missing: "원문에서 확인되지 않은 필수 전략 조건이 남아 있습니다.",
  independent_entry_signal_missing: "독립 전략의 LONG/SHORT 방향이 없습니다.",
  independent_executable_entry_missing: "독립 전략의 실행 가능한 진입 조건이 없습니다.",
  confirm_executable_entry_missing: "원문에서 실행 가능한 확인 조건을 만들지 못했습니다. 원문을 보완하거나 Level 3·4에서 NoahAI 기본 진입 + 사용자 위험·청산값 방식으로 명시적으로 저장하세요.",
  independent_exit_policy_cannot_inherit_noah: "독립 전략은 NoahAI 청산정책을 상속할 수 없습니다.",
  inherited_exit_policy_conflicts_with_strategy_rates: "NoahAI 청산 상속과 전략 고정 TP/SL이 동시에 선언됐습니다.",
  strategy_exit_rates_missing: "전략 자체 청산을 선택했지만 TP와 SL 한 쌍이 없습니다.",
  exit_rate_contract_missing_or_invalid: "TP/SL 단위가 없거나 허용 범위를 벗어났습니다.",
  engine_settings_contract_invalid: "레버리지·포지션 비중·신호 임계값 중 하나가 허용 범위를 벗어났습니다. 값은 자동 보정되지 않습니다.",
  source_grounding_stale_after_execution_edit: "분석 뒤 진입·청산·TP/SL 실행값이 바뀌었습니다. 변경한 원문으로 다시 분석해 근거를 갱신하세요.",
  source_grounding_invalid: "원문과 실행 규칙의 근거 상태가 올바르지 않습니다. 원문 분석을 다시 실행하세요.",
  source_grounding_user_override_not_confirmed: "원문과 다른 사용자 선언 규칙으로 저장하려면 Level 3·4 확인란을 선택하세요.",
};

function readinessReason(value: unknown): string {
  const key = String(value ?? "");
  return READINESS_REASON_LABELS[key] ?? key;
}

function strategyVersionTime(value: unknown): string {
  const text = String(value ?? "").trim();
  if (!text) return "생성 시각 기록 없음";
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return `생성 ${text}`;
  return `생성 ${parsed.toLocaleString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false })}`;
}

export function StrategyStudio({ client, service, source = "", onAskAssistant, onOpenSettings, onOpenDifficultySettings, settingsRevision = 0, assistantDraft, onAssistantDraftConsumed }: { client: GatewayClient; service: "blockchain" | "stock"; source?: string; onAskAssistant?: (question: string) => void; onOpenSettings?: () => void; onOpenDifficultySettings?: () => void; settingsRevision?: number; assistantDraft?: StrategyAssistantDraft | null; onAssistantDraftConsumed?: () => void }) {
  const [catalog, setCatalog] = useState<StrategyCatalog | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("새 AI 전략");
  const [scope, setScope] = useState<"binance" | "unified">("binance");
  const [executionTarget, setExecutionTarget] = useState(() => defaultExecutionTarget(service, source));
  const [rulesText, setRulesText] = useState(JSON.stringify(STARTER_RULES, null, 2));
  const [repairVisible, setRepairVisible] = useState(false);
  const [decisionTimeframe, setDecisionTimeframe] = useState("");
  const repairRef = useRef<HTMLDivElement>(null);
  function showRepairInstructions() {
    setGuidedOpen(false);
    setRepairVisible(true);
    requestAnimationFrame(() => requestAnimationFrame(() => {
      repairRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
      repairRef.current?.focus({ preventScroll: true });
    }));
  }
  const [sourceKind, setSourceKind] = useState("auto");
  const [sourceValue, setSourceValue] = useState("");
  const [sourceReferenceInput, setSourceReferenceInput] = useState("");
  const [sourceReference, setSourceReference] = useState("web-ui://strategy-studio");
  const [sourceSummary, setSourceSummary] = useState("");
  const [sourceAnalysis, setSourceAnalysis] = useState<Record<string, any> | null>(null);
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [beginnerPreset, setBeginnerPreset] = useState("auto_regime");
  const [versionTarget, setVersionTarget] = useState("");
  const [marketRegimes, setMarketRegimes] = useState<string[]>(["all"]);
  const [regimeScope, setRegimeScope] = useState("market");
  const [priority, setPriority] = useState("5");
  const [signalMode, setSignalMode] = useState("confirm");
  const [entrySignal, setEntrySignal] = useState("auto");
  const [exitPolicyMode, setExitPolicyMode] = useState("inherit_noah_base");
  const [riskPerTrade, setRiskPerTrade] = useState("0.5");
  const [maxMargin, setMaxMargin] = useState("10");
  const [leverageCap, setLeverageCap] = useState("3");
  const [maxConcurrentPositions, setMaxConcurrentPositions] = useState("3");
  const [conflictFallback, setConflictFallback] = useState("기본 노아AI에 맡김");
  const [riskPolicyPreset, setRiskPolicyPreset] = useState<keyof typeof RISK_POLICY_PRESETS | "custom">("standard");
  const [resultView, setResultView] = useState("Level 2 핵심값");
  const [featureProfile, setFeatureProfile] = useState("standard");
  const [featureViewLevel, setFeatureViewLevel] = useState(2);
  const [showSafeSteps, setShowSafeSteps] = useState(false);
  const [showLevelGuide, setShowLevelGuide] = useState(false);
  const [paperModeEnabled, setPaperModeEnabled] = useState(true);
  const [parallelPaperEnabled, setParallelPaperEnabled] = useState(false);
  const [mentorOpen, setMentorOpen] = useState(false);
  const [mentorProfile, setMentorProfile] = useState<Record<string, unknown>>({
    asset_class: "crypto", capital_band: "small", max_loss_percent: 0.5,
    review_frequency: "daily", trade_frequency: "medium", leverage_allowed: false,
    experience_level: "beginner", paper_ready: true,
  });
  const [mentorCandidates, setMentorCandidates] = useState<Array<Record<string, any>>>([]);
  const [guidedOpen, setGuidedOpen] = useState(false);
  const [guidedStep, setGuidedStep] = useState(1);
  const [guidedQuestion, setGuidedQuestion] = useState(0);
  const [guidedMethod, setGuidedMethod] = useState<GuidedStartMethod>("");
  const [guidedAnswers, setGuidedAnswers] = useState({ tradeFrequency: "medium", maxLossPercent: 0.5 });
  const [guidedVersion, setGuidedVersion] = useState<StrategyVersion | null>(null);
  const [guidedCompleted, setGuidedCompleted] = useState(false);
  const [guidedCompletedOnce, setGuidedCompletedOnce] = useState(false);
  const [userDeclaredOverride, setUserDeclaredOverride] = useState(false);
  const [draftValidationIssues, setDraftValidationIssues] = useState<Array<Record<string, string>>>([]);
  const [authoringMode, setAuthoringMode] = useState<StrategyAuthoringMode>("source_faithful");
  const [confirmedSupplement, setConfirmedSupplement] = useState("");
  const [clarificationAnswers, setClarificationAnswers] = useState<Record<string, string>>({});
  const [assistantDraftText, setAssistantDraftText] = useState("");
  const assistantDraftIdRef = useRef(0);
  const assistantDraftPanelRef = useRef<HTMLElement>(null);
  const [accountRiskPolicy, setAccountRiskPolicy] = useState({
    mode: "account_risk",
    riskPerTrade: 0.5,
    maxMargin: 10,
    defaultLeverage: 1,
    maxPositions: 3,
  });

  useEffect(() => {
    const stock = service === "stock";
    setDecisionTimeframe("");
    setScope(stock ? "unified" : "binance");
    setExecutionTarget(defaultExecutionTarget(service, source));
    setVersionTarget("");
    setSourceAnalysis(null);
    setUserDeclaredOverride(false);
    setAuthoringMode("source_faithful");
    setConfirmedSupplement("");
    setClarificationAnswers({});
    setMarketRegimes(["all"]);
    setRegimeScope("market");
    setRulesText(JSON.stringify({
      ...STARTER_RULES,
      target_scope: defaultExecutionTarget(service, source),
    }, null, 2));
    setGuidedVersion(null);
    setGuidedCompleted(false);
  }, [service]);

  useEffect(() => {
    if (!assistantDraft || assistantDraft.service !== service || assistantDraft.id === assistantDraftIdRef.current) return;
    assistantDraftIdRef.current = assistantDraft.id;
    setAssistantDraftText(assistantDraft.text);
    setAuthoringMode("guided_clarification");
    setMessage("AI 답변을 검토 영역으로 가져왔습니다. 실행값이 아니므로 내용을 확인·수정한 뒤 보완 근거로 확정하세요.");
    window.requestAnimationFrame(() => assistantDraftPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }));
  }, [assistantDraft, service]);

  useEffect(() => {
    try {
      setGuidedCompletedOnce(window.localStorage.getItem(`noahai.strategy-studio-guided.${service}`) === "done");
    } catch (_) {
      setGuidedCompletedOnce(false);
    }
  }, [service]);

  function refresh() {
    setBusy(true);
    client.strategies().then((next) => setCatalog({ ...next, strategies: next.strategies.map((group) => ({
      ...group, versions: group.versions.filter((version) => {
        const target = String(version.rules?.target_scope ?? "asset:crypto");
        return target === "asset:all" || (service === "stock"
          ? target === "asset:stock" || target === "asset:etf" || target.startsWith("broker:")
          : target === "asset:crypto" || target.startsWith("exchange:"));
      }),
    })).filter((group) => group.versions.length) })).catch((error: unknown) => setMessage(error instanceof Error ? error.message : "전략을 불러오지 못했습니다.")).finally(() => setBusy(false));
  }

  function loadVersionDraft(strategyKey: string) {
    const group = catalog?.strategies.find((item) => item.strategy_key === strategyKey && item.scope === scope);
    const version = group?.versions.at(-1);
    setVersionTarget(strategyKey);
    if (!version) return;
    const rules = version.rules ?? {};
    setName(version.name);
    setRulesText(JSON.stringify(rules, null, 2));
    setExecutionTarget(String(rules.target_scope ?? allCompatibleTarget));
    setMarketRegimes(normalizeMarketRegimes(rules.market_regimes));
    setRegimeScope(String(rules.regime_scope ?? "market"));
    setPriority(String(rules.priority ?? 5));
    setSignalMode(String(rules.signal_mode ?? "confirm"));
    setEntrySignal(String(rules.entry_signal ?? "auto"));
    setExitPolicyMode(String(rules.exit_policy?.mode ?? "inherit_noah_base"));
    setRiskPerTrade(String(rules.risk_model?.risk_per_trade_percent ?? 1));
    setMaxMargin(String(rules.risk_model?.max_margin_usage_percent ?? 20));
    setLeverageCap(String(rules.risk_model?.max_leverage ?? 1));
    setMaxConcurrentPositions(String(rules.risk_model?.max_concurrent_positions ?? 3));
    setRiskPolicyPreset(["standard", "conservative", "active", "custom"].includes(String(rules.risk_policy_preset)) ? rules.risk_policy_preset : "custom");
    setConflictFallback(String(rules.conflict_fallback ?? "NoahAI 기본 전략으로 전환"));
    setDecisionTimeframe(String(rules.decision_timeframe ?? rules.timeframe ?? ""));
    setSourceReference(version.source_reference ?? "web-ui://strategy-version");
    setSourceKind("text");
    setSourceAnalysis(null);
    setUserDeclaredOverride(false);
    setMessage("기존 규칙을 새 버전 초안으로 불러왔습니다. 변경한 실행값은 사용자 선언을 확인한 뒤 저장하세요. 승인·검증·적용 이력은 승계되지 않습니다.");
  }

  function changeExecutionTarget(nextTarget: string) {
    setExecutionTarget(nextTarget);
    if (!versionTarget) setScope(nextTarget === "exchange:binance" ? "binance" : "unified");
    setSourceAnalysis(null);
    setDraftValidationIssues([]);
    setMessage("전략 호환 범위를 변경했습니다. 원문과 실행 규칙을 새 범위로 다시 분석해야 합니다.");
  }

  async function runMentor() {
    setBusy(true);
    try {
      const result = await client.strategyMentor(mentorProfile);
      const candidates = Array.isArray(result.candidates) ? result.candidates : [];
      setMentorCandidates(candidates);
      setMessage(candidates.length
        ? "AI 멘토가 검토용 후보를 만들었습니다. 후보의 실행 준비 표시와 규칙을 확인한 뒤 저장·승인·과거 재생·PAPER를 진행하세요."
        : "인터뷰 값의 범위를 확인하세요. 거래당 최대 허용 손실률은 0.05~5%입니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "AI 멘토 후보를 만들지 못했습니다.");
    } finally { setBusy(false); }
  }

  function loadMentorCandidate(candidate: Record<string, any>) {
    const analysis = candidate.draft_analysis && typeof candidate.draft_analysis === "object"
      ? candidate.draft_analysis as Record<string, any>
      : null;
    const candidateRules = analysis?.rules && typeof analysis.rules === "object"
      ? analysis.rules as Record<string, any>
      : candidate.draft_rules && typeof candidate.draft_rules === "object"
        ? candidate.draft_rules as Record<string, any>
        : null;
    const regimes = normalizeMarketRegimes(candidate.suitable_regimes ?? candidateRules?.market_regimes);
    const candidateRisk = candidateRules?.risk_model && typeof candidateRules.risk_model === "object"
      ? candidateRules.risk_model as Record<string, any>
      : {};
    const candidateEngine = candidateRules?.engine_settings && typeof candidateRules.engine_settings === "object"
      ? candidateRules.engine_settings as Record<string, any>
      : {};
    setName(String(candidate.name ?? "AI 멘토 검토 후보"));
    setSourceKind("text");
    setSourceValue(String(candidate.source_text ?? ""));
    setSourceReferenceInput("");
    setSourceReference(`noahai://mentor/${String(candidate.preset_key ?? "candidate")}`);
    setSourceSummary("NoahAI 관리 템플릿에서 만든 검토용 실행 초안입니다. 자동 저장·승인·적용되지 않습니다.");
    setSourceAnalysis(analysis);
    setUserDeclaredOverride(false);
    setAuthoringMode("source_faithful");
    setConfirmedSupplement("");
    setClarificationAnswers({});
    setMarketRegimes(regimes);
    if (candidateRules) {
      setDecisionTimeframe(String(candidateRules.decision_timeframe ?? ""));
      setRulesText(JSON.stringify({
        ...candidateRules,
        target_scope: executionTarget,
        market_conditions: marketRegimeLabels(regimes),
        market_regimes: regimes,
        regime_scope: regimeScope,
      }, null, 2));
      const mode = String(candidateRules.signal_mode ?? "independent");
      setSignalMode(mode);
      setEntrySignal(String(candidateRules.entry_signal || "auto"));
      setExitPolicyMode("strategy_owned");
      setRiskPerTrade(String(candidateRisk.risk_per_trade_percent ?? mentorProfile.max_loss_percent ?? 0.5));
      setMaxMargin(String(candidateRisk.max_margin_usage_percent ?? Number(candidateEngine.position_size ?? 0.1) * 100));
      setLeverageCap(String(candidateRisk.max_leverage ?? candidateEngine.leverage ?? 1));
      setMaxConcurrentPositions(String(candidateRisk.max_concurrent_positions ?? 3));
      setRiskPolicyPreset("custom");
      setConflictFallback("커스텀 신규 진입 일시정지");
    }
    setMentorOpen(false);
    setMessage(analysis?.ready_for_execution === true
      ? "실행 계약을 통과한 관리 템플릿 초안을 불러왔습니다. 규칙·TP/SL·위험예산을 검토한 뒤 저장·승인·PAPER를 진행하세요."
      : "교육용 후보를 불러왔습니다. 누락 조건을 완성하고 AI 분석을 다시 실행해야 저장할 수 있습니다.");
  }

  function openGuidedTour() {
    setGuidedOpen(true);
  }

  function restartGuidedTour() {
    setGuidedStep(1);
    setGuidedQuestion(0);
    setGuidedMethod("");
    setGuidedAnswers({ tradeFrequency: "medium", maxLossPercent: 0.5 });
    setGuidedVersion(null);
    setGuidedCompleted(false);
    setMessage("따라하기 안내만 처음부터 다시 시작합니다. 저장된 전략과 PAPER 근거는 변경하지 않았습니다.");
  }

  function chooseGuidedMethod(method: Exclude<GuidedStartMethod, "">) {
    setGuidedMethod(method);
    setGuidedQuestion(0);
    setGuidedVersion(null);
    setGuidedCompleted(false);
    setGuidedStep(2);
  }

  function advanceGuidedQuestion() {
    if (guidedQuestion < 2) {
      setGuidedQuestion((current) => current + 1);
      return;
    }
    setGuidedStep(3);
  }

  function finishGuidedTour(messageText: string) {
    setGuidedCompleted(true);
    setGuidedCompletedOnce(true);
    setGuidedStep(5);
    setMessage(messageText);
    try {
      window.localStorage.setItem(`noahai.strategy-studio-guided.${service}`, "done");
    } catch (_) {
      // 완료 표시는 편의 기능일 뿐이므로 브라우저 저장 실패가 전략 흐름을 막지 않는다.
    }
  }
  useEffect(refresh, [client]);
  useEffect(() => {
    client.settings().then((snapshot) => {
      const valueOf = (path: string, fallback: unknown) => snapshot.fields.find((item) => item.path === path)?.value ?? fallback;
      const rawProfile = String(snapshot.fields.find((item) => item.path === "ai_custom_features.profile")?.value || "standard");
      const normalizedProfile = rawProfile === "laboratory" ? "lab" : rawProfile;
      const viewLevel = normalizedProfile === "beginner" ? 1 : normalizedProfile === "lab" ? 4 : normalizedProfile === "advanced" ? 3 : 2;
      setFeatureProfile(normalizedProfile);
      setPaperModeEnabled(Boolean(snapshot.fields.find((item) => item.path === "paper_trading")?.value));
      setParallelPaperEnabled(Boolean(valueOf("parallel_strategy_paper_validation.enabled", false)));
      setFeatureViewLevel(viewLevel);
      setResultView(levelView(viewLevel));
      setAccountRiskPolicy({
        mode: String(valueOf("position_sizing_policy.mode", "legacy_venue")),
        riskPerTrade: Number(valueOf("position_sizing_policy.risk_per_trade_percent", 0.5)),
        maxMargin: Number(valueOf("position_sizing_policy.max_margin_usage_percent", 10)),
        defaultLeverage: Number(valueOf("default_leverage", 1)),
        maxPositions: Number(valueOf("max_positions", 3)),
      });
    }).catch(() => {
      setFeatureProfile("standard");
      setFeatureViewLevel(2);
    });
  }, [client, settingsRevision]);

  function loadBeginnerPresetByKey(presetKey: string) {
    const preset = BEGINNER_PRESETS.find((item) => item.key === presetKey) ?? BEGINNER_PRESETS[0];
    setBeginnerPreset(preset.key);
    if (preset.key === "auto_regime") {
      setName("새 AI 전략");
      setSourceKind("auto");
      setSourceFile(null);
      setSourceReferenceInput("");
      setSourceValue("");
      setSourceReference("web-ui://strategy-studio");
      setSourceSummary("기본 NoahAI 자동 대응은 커스텀 전략을 만들지 않습니다.");
      setSourceAnalysis(null);
      setUserDeclaredOverride(false);
      setAuthoringMode("noah_delegate");
      setConfirmedSupplement("");
      setClarificationAnswers({});
      setMarketRegimes(["all"]);
      setMessage("기본 NoahAI를 사용하려면 전략을 저장할 필요가 없습니다. PAPER/LIVE와 거래소 설정을 확인한 뒤 해당 거래소 카드에서 시작하세요. 전략 제작을 연습하려면 관리형 예제를 선택하세요.");
      return;
    }
    setName(preset.name);
    setSourceKind("text");
    setSourceFile(null);
    setSourceReferenceInput("");
    setSourceValue(preset.source);
    setSourceReference(`noahai://beginner-preset/${preset.key}`);
    setSourceSummary(`${preset.label} 검토용 초안을 불러왔습니다. 자동 저장·승인·적용되지 않습니다.`);
    setSourceAnalysis(null);
    setUserDeclaredOverride(false);
    setAuthoringMode("source_faithful");
    setConfirmedSupplement("");
    setClarificationAnswers({});
    setMarketRegimes(["all"]);
    setMessage("원문과 적용 범위를 검토한 뒤 규칙 초안을 만들고, 승인·과거 재생·PAPER를 순서대로 진행하세요.");
  }

  function loadBeginnerPreset() {
    loadBeginnerPresetByKey(beginnerPreset);
  }

  async function prepareGuidedDraft(requestedMethod: GuidedStartMethod = guidedMethod) {
    if (!requestedMethod) return;
    setGuidedMethod(requestedMethod);
    if (requestedMethod === "noah") {
      finishGuidedTour("기본 NoahAI 운용 경로를 확인했습니다. 커스텀 전략을 만들거나 적용하지 않았습니다.");
      return;
    }
    if (requestedMethod === "import") {
      setSourceKind("auto");
      setAuthoringMode("guided_clarification");
      setGuidedStep(4);
      setMessage("전략 설명을 붙여 넣거나 파일을 선택한 뒤 분석 버튼을 누르세요. 선택 내용은 자동 저장·승인되지 않습니다.");
      return;
    }
    setBusy(true);
    try {
      const result = await client.strategyMentor({
        asset_class: service === "stock" ? "stock" : "crypto",
        capital_band: "small",
        max_loss_percent: guidedAnswers.maxLossPercent,
        review_frequency: guidedAnswers.tradeFrequency === "high" ? "intraday" : guidedAnswers.tradeFrequency === "low" ? "weekly" : "daily",
        trade_frequency: guidedAnswers.tradeFrequency,
        leverage_allowed: false,
        experience_level: "beginner",
        paper_ready: true,
      });
      const candidate = Array.isArray(result.candidates) ? result.candidates[0] : null;
      if (!candidate) throw new Error("현재 답변으로 만들 수 있는 관리형 예제 후보가 없습니다.");
      loadMentorCandidate(candidate);
      setGuidedStep(4);
      setMessage("외부 AI 호출 없이 관리형 예제 초안을 불러왔습니다. 쉬운 설명과 실제 실행 규칙을 확인한 뒤 저장하세요.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "관리형 예제를 준비하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  function resetDraft() {
    const stock = service === "stock";
    setDecisionTimeframe("");
    const nextTarget = defaultExecutionTarget(service, source);
    setName("새 AI 전략");
    setScope(stock ? "unified" : "binance");
    setExecutionTarget(nextTarget);
    setRulesText(JSON.stringify({
      ...STARTER_RULES,
      target_scope: nextTarget,
    }, null, 2));
    setSourceKind("auto");
    setSourceValue("");
    setSourceReferenceInput("");
    setSourceReference("web-ui://strategy-studio");
    setSourceSummary("");
    setSourceAnalysis(null);
    setUserDeclaredOverride(false);
    setAuthoringMode("source_faithful");
    setConfirmedSupplement("");
    setClarificationAnswers({});
    setSourceFile(null);
    setBeginnerPreset("auto_regime");
    setVersionTarget("");
    setMarketRegimes(["all"]);
    setRegimeScope("market");
    setPriority("5");
    setSignalMode("confirm");
    setEntrySignal("auto");
    setExitPolicyMode("inherit_noah_base");
    setRiskPerTrade("0.5");
    setMaxMargin("10");
    setLeverageCap("3");
    setConflictFallback("기본 노아AI에 맡김");
    setRiskPolicyPreset("standard");
    setResultView(levelView(featureViewLevel));
    setMessage("입력 중인 초안만 초기화했습니다. 저장된 전략 버전은 변경하지 않았습니다.");
  }

  function toggleMarketRegime(value: string) {
    if (value === "all") {
      setMarketRegimes(["all"]);
      return;
    }
    setMarketRegimes((current) => {
      const specific = current.filter((item) => item !== "all");
      const next = specific.includes(value)
        ? specific.filter((item) => item !== value)
        : [...specific, value];
      return next.length ? next : ["all"];
    });
  }

  function issueField(code: unknown): string {
    const normalized = String(code ?? "");
    return normalized.startsWith("missing_required_rule:")
      ? normalized.split(":", 2)[1]
      : normalized;
  }

  function canInsertConfirmedSupplement(code: unknown): boolean {
    return ["position_size", "market_conditions"].includes(issueField(code));
  }

  function clarificationKey(item: Record<string, any>, index: number): string {
    return String(item.id || `${item.code || "question"}:${index}`);
  }

  function mergeConfirmedSupplement(current: string, lines: string[]): string {
    const existing = current.split("\n").map((item) => item.trim()).filter(Boolean);
    return [...existing, ...lines.map((item) => item.trim()).filter((item) => item && !existing.includes(item))].join("\n");
  }

  async function insertConfirmedSupplement(code: unknown) {
    const field = issueField(code);
    let line = "";
    if (field === "position_size") {
      line = `거래당 계좌 손실 ${riskPerTrade}%, ${service === "stock" ? "종목당 투자 비중" : "증거금 사용"}은 최대 ${maxMargin}%.`;
    } else if (field === "market_conditions") {
      const selected = marketRegimeLabels(marketRegimes);
      line = marketRegimes.includes("all")
        ? "사용 시장상황: 모든 시장상황 (실행 시 NoahAI가 국면 적합성을 다시 검사)."
        : `사용 시장상황: ${selected.join("·")}에서만 사용.`;
    }
    if (!line) return;
    const nextSupplement = mergeConfirmedSupplement(confirmedSupplement, [line]);
    setConfirmedSupplement(nextSupplement);
    setDraftValidationIssues([]);
    setMessage(
      `AI가 추측한 값이 아니라 현재 화면에서 사용자가 선택한 값입니다. 현재 선택값을 보완 근거로 추가했습니다: ${line} 원본 파일은 바뀌지 않으며 지금 다시 분석합니다.`,
    );
    await analyzeSource(nextSupplement);
  }

  async function applyAssistantDraft() {
    const reviewed = assistantDraftText.trim();
    if (!reviewed) {
      setMessage("AI 답변에서 참고할 내용을 직접 확인하거나 수정한 뒤 적용하세요.");
      return;
    }
    const nextSupplement = mergeConfirmedSupplement(confirmedSupplement, [
      `사용자 확인 · AI 어시스턴트에서 가져와 검토한 보완 답변: ${reviewed}`,
    ]);
    setConfirmedSupplement(nextSupplement);
    setAssistantDraftText("");
    setDraftValidationIssues([]);
    onAssistantDraftConsumed?.();
    setMessage("검토한 AI 답변을 원본과 별도인 사용자 확인 근거로 확정했습니다. 지금 결정형 컴파일러로 다시 분석합니다.");
    await analyzeSource(nextSupplement);
  }

  async function applyClarificationAnswers(questions: Array<Record<string, any>>) {
    const confirmedLines = questions.flatMap((item, index) => {
      if (String(item.resolution || "") !== "user_answer") return [];
      const answer = String(clarificationAnswers[clarificationKey(item, index)] || "").trim();
      return answer ? [`사용자 확인 · ${String(item.title || item.field || "전략 조건")}: ${answer}`] : [];
    });
    if (!confirmedLines.length) {
      setMessage("먼저 한 개 이상의 질문에 자신의 전략 조건을 답해 주세요. AI 예시는 자동으로 선택되지 않습니다.");
      return;
    }
    const nextSupplement = mergeConfirmedSupplement(confirmedSupplement, confirmedLines);
    setConfirmedSupplement(nextSupplement);
    setClarificationAnswers({});
    setDraftValidationIssues([]);
    setMessage("사용자가 직접 답한 조건을 별도 근거로 확정했습니다. 원본은 바꾸지 않고 지금 다시 분석합니다.");
    await analyzeSource(nextSupplement);
  }

  async function createStrategy() {
    setBusy(true);
    setDraftValidationIssues([]);
    try {
      const parsedRules = JSON.parse(rulesText) as Record<string, unknown>;
      if (!parsedRules.decision_timeframe && !parsedRules.timeframe && !decisionTimeframe) {
        setDraftValidationIssues([{ code: "decision_timeframe_missing", title: "전략 판단 시간봉을 확인하세요", action: "원문이 사용하는 봉을 화면의 전략 판단 시간봉에서 선택하세요.", example: "1분 전략은 1m, 일봉 주식 전략은 1d" }]);
        setMessage("저장 전에 전략 판단 시간봉을 선택하세요.");
        setBusy(false);
        return;
      }
      const originalGrounding = parsedRules.source_grounding && typeof parsedRules.source_grounding === "object"
        ? parsedRules.source_grounding as Record<string, unknown>
        : {};
      const rules = {
        ...parsedRules,
        decision_timeframe: parsedRules.decision_timeframe || parsedRules.timeframe || decisionTimeframe,
        execution_timeframe: parsedRules.execution_timeframe || parsedRules.decision_timeframe || parsedRules.timeframe || decisionTimeframe,
        target_scope: executionTarget,
        market_conditions: marketRegimeLabels(marketRegimes),
        market_regimes: marketRegimes,
        regime_scope: regimeScope,
        priority: Number(priority),
        signal_mode: signalMode,
        ...(entrySignal !== "auto" ? { entry_signal: entrySignal } : {}),
        exit_policy: { ...(parsedRules.exit_policy as Record<string, unknown> ?? {}), mode: signalMode === "independent" ? "strategy_owned" : exitPolicyMode },
        risk_model: {
          ...(parsedRules.risk_model as Record<string, unknown> ?? {}),
          risk_per_trade_percent: Number(riskPerTrade),
          max_margin_usage_percent: Number(maxMargin),
          max_leverage: service === "stock" ? 1 : Number(leverageCap),
          max_concurrent_positions: Number(maxConcurrentPositions),
        },
        risk_policy_preset: riskPolicyPreset,
        conflict_fallback: conflictFallback,
        regime_transition: conflictFallback === "커스텀 신규 진입 일시정지" ? "pause" : "delegate_to_noah",
        ...(userDeclaredOverride ? {
          source_grounding: {
            ...originalGrounding,
            status: "user_declared_override",
            confirmed_by_user: true,
            base_compiler_contract_sha256: String(originalGrounding.compiler_contract_sha256 ?? ""),
          },
        } : {}),
      };
      const reference = sourceReference || sourceReferenceInput.trim() || "web-ui://strategy-studio";
      const finalValidation = await client.validateStrategyDraft({
        rules,
        compiler_issues: Array.isArray(parsedRules.compiler_issues) ? parsedRules.compiler_issues : [],
      });
      if (finalValidation.ready !== true) {
        const blockingDetails = Array.isArray(finalValidation.blocking_details)
          ? finalValidation.blocking_details.filter((item: unknown) => item && typeof item === "object")
          : [];
        setDraftValidationIssues(blockingDetails as Array<Record<string, string>>);
        setMessage(`최종 규칙 재검증 실패 · 아래 ${blockingDetails.length || 1}개 항목을 확인하세요.`);
        setBusy(false);
        return;
      }
      const validatedRules = finalValidation.rules && typeof finalValidation.rules === "object"
        ? finalValidation.rules as Record<string, unknown>
        : rules;
      const created = await client.submitStrategy({
        scope, name, rules: validatedRules,
        source_kind: normalizedSubmitSourceKind(String(sourceAnalysis?.source?.kind ?? sourceKind), reference),
        source_reference: reference,
        strategy_key: versionTarget || undefined,
      });
      if (guidedOpen) {
        setGuidedVersion(created as unknown as StrategyVersion);
        setGuidedStep(4);
      }
      setDraftValidationIssues([]);
      setMessage("전략 새 버전을 만들었습니다. XAI와 누락 조건을 확인한 뒤 승인하세요.");
      refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "전략 생성에 실패했습니다.");
      setBusy(false);
    }
  }

  async function analyzeSource(supplementOverride?: string) {
    if (!sourceReferenceInput.trim() && !sourceValue.trim() && !sourceFile) { setMessage("전략 설명·Pine·URL을 입력하거나 파일을 선택하세요."); return; }
    setBusy(true); setMessage(""); setDraftValidationIssues([]);
    try {
      let value = sourceReferenceInput.trim() || sourceValue;
      let encoding = "text";
      let fileName = "";
      if (sourceFile) {
        const bytes = new Uint8Array(await sourceFile.arrayBuffer());
        let binary = "";
        for (let offset = 0; offset < bytes.length; offset += 0x8000) {
          binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
        }
        value = btoa(binary); encoding = "base64"; fileName = sourceFile.name;
      }
      const supplement = typeof supplementOverride === "string" ? supplementOverride : confirmedSupplement;
      const result = await client.analyzeStrategySource({
        source_kind: sourceKind,
        value,
        encoding,
        file_name: fileName,
        supplemental_text: supplement,
        authoring_mode: authoringMode,
      });
      const suggestion = (result.market_regime_suggestion ?? {}) as Record<string, unknown>;
      const suggestedRegimes = suggestion.auto_select === true
        ? normalizeMarketRegimes(suggestion.regimes)
        : ["all"];
      setMarketRegimes(suggestedRegimes);
      setName(String(result.name ?? name));
      const analyzedSignalMode = String(result.rules?.signal_mode ?? "confirm");
      const rawExitPolicy = result.rules?.exit_policy;
      const analyzedExitPolicy = typeof rawExitPolicy === "object" && rawExitPolicy
        ? String(rawExitPolicy.mode ?? "inherit_noah_base")
        : String(rawExitPolicy ?? "inherit_noah_base");
      setSignalMode(analyzedSignalMode);
      setEntrySignal(String(result.rules?.entry_signal || "auto"));
      setExitPolicyMode(analyzedSignalMode === "independent" ? "strategy_owned" : analyzedExitPolicy);
      const analyzedRisk = result.rules?.risk_model && typeof result.rules.risk_model === "object"
        ? result.rules.risk_model as Record<string, unknown>
        : {};
      const analyzedEngine = result.rules?.engine_settings && typeof result.rules.engine_settings === "object"
        ? result.rules.engine_settings as Record<string, unknown>
        : {};
      const parsedRisk = Number(analyzedRisk.risk_per_trade_percent);
      const parsedMargin = Number(
        analyzedRisk.max_margin_usage_percent
        ?? (Number(analyzedEngine.position_size) > 0 ? Number(analyzedEngine.position_size) * 100 : 0),
      );
      const parsedLeverage = Number(analyzedRisk.max_leverage ?? analyzedEngine.leverage);
      if (Number.isFinite(parsedRisk) && parsedRisk > 0) setRiskPerTrade(String(parsedRisk));
      if (Number.isFinite(parsedMargin) && parsedMargin > 0) setMaxMargin(String(parsedMargin));
      if (service !== "stock" && Number.isFinite(parsedLeverage) && parsedLeverage > 0) setLeverageCap(String(parsedLeverage));
      if (parsedRisk > 0 || parsedMargin > 0 || parsedLeverage > 0) setRiskPolicyPreset("custom");
      setRulesText(JSON.stringify({
        ...(result.rules ?? STARTER_RULES),
        target_scope: executionTarget,
        market_conditions: marketRegimeLabels(suggestedRegimes),
        market_regimes: suggestedRegimes,
        regime_scope: regimeScope,
      }, null, 2));
      setSourceReference(String(result.source?.reference ?? (fileName || "pasted")));
      setSourceSummary(`${String(result.summary ?? "원본 분석 완료")} · 누락 ${Number(result.missing_conditions?.length ?? 0)}개 · ${result.provider_called ? "외부 AI 사용" : "규칙 기반 추출"} · ${suggestion.auto_select === true ? `명시 국면 ${marketRegimeLabels(suggestedRegimes).join("·")} 추천 적용` : "국면 근거 없음 → NoahAI 판단"}`);
      setSourceAnalysis(result);
      setClarificationAnswers({});
      setUserDeclaredOverride(false);
      setMessage(result.ready_for_execution === true
        ? "원본과 사용자 확인 답변에서 실행 가능한 규칙 초안을 만들었습니다. 저장 전 원문-규칙 추적과 실제 적용값을 확인하세요."
        : authoringMode === "guided_clarification"
          ? "아직 확인할 조건이 있습니다. 아래 질문에 자신의 기준으로 답한 뒤 다시 분석하세요. AI 예시는 자동 적용되지 않습니다."
          : "원본 근거에서 규칙 초안을 만들었습니다. 누락 조건은 추측하지 않았으며 질문으로 보완하거나 원문을 수정할 수 있습니다.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "전략 원본 분석에 실패했습니다.");
    } finally { setBusy(false); }
  }

  async function exportPackage(targetScope: string, version: StrategyVersion) {
    setBusy(true);
    try {
      const result = await client.exportStrategyPackage(targetScope, version.strategy_key, version.version_id);
      const packageJson = typeof result.package_json === "string"
        ? result.package_json
        : JSON.stringify(result.package, null, 2);
      const blob = new Blob([packageJson], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = String(result.file_name ?? `${version.name}.noahstrategy`); anchor.click();
      URL.revokeObjectURL(url); setMessage("민감정보·승인·활성 상태를 제외한 검토용 패키지를 내보냈습니다.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "패키지 내보내기에 실패했습니다."); }
    finally { setBusy(false); }
  }

  async function exportExecutionEvidence(targetScope: string, version: StrategyVersion) {
    setBusy(true);
    try {
      const result = await client.exportStrategyExecutionEvidence(
        targetScope, version.strategy_key, version.version_id,
      );
      const evidenceJson = typeof result.evidence_json === "string"
        ? result.evidence_json
        : JSON.stringify(result.evidence, null, 2);
      const blob = new Blob([evidenceJson], { type: "application/json;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = String(result.file_name ?? `${version.name}_paper_evidence.json`);
      anchor.click();
      URL.revokeObjectURL(url);
      const count = Number(result.evidence?.evidence_scope?.trade_count ?? 0);
      setMessage(
        `이 버전의 PAPER 검증 거래 ${count}건을 계정 로컬 파일로 내보냈습니다. `
        + "기록되지 않은 과거 항목은 0이 아니라 비어 있으며 허브로 자동 전송되지 않습니다.",
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "검증 거래 내보내기에 실패했습니다.");
    } finally { setBusy(false); }
  }

  async function importPackage(file: File | null) {
    if (!file) return;
    setBusy(true);
    try {
      const parsed = JSON.parse(await file.text()) as Record<string, unknown>;
      await client.importStrategyPackage(scope, file.name, parsed);
      setMessage("SHA-256을 검증해 비활성 검토 버전으로 가져왔습니다. 승인·검증·PAPER를 다시 거쳐야 합니다.");
      refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "패키지 가져오기에 실패했습니다."); setBusy(false); }
  }

  async function rollback(targetScope: string, version: StrategyVersion) {
    if (!window.confirm(`v${version.version} 버전으로 되돌릴까요?\n\n검증 이력이 있는 이 버전을 새 활성 기준으로 선택합니다. 거래 기록은 삭제하지 않습니다.`)) return;
    setBusy(true);
    try {
      await client.strategyAction({ scope: targetScope, strategy_key: version.strategy_key, version_id: version.version_id, action: "rollback", live_confirmation: false, operation_mode: "standard" });
      setMessage("검증된 이전 버전으로 롤백했습니다."); refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "롤백에 실패했습니다."); setBusy(false); }
  }

  async function runAction(version: StrategyVersion, targetScope: string, forcedAction?: "start_paper" | "restart_paper") {
    const replayApplicable = historicalReplayApplicable(version);
    const historicalValidation = !version.active && replayApplicable && ["approved", "execution_rejected"].includes(version.status);
    const directPaperValidation = !version.active && !replayApplicable && ["approved", "execution_rejected"].includes(version.status);
    const action = forcedAction ?? (historicalValidation
      ? "validate"
      : directPaperValidation
        ? "start_paper"
      : version.active
        ? "deactivate"
        : (version.paper_observing || version.status === "paper_observing")
          ? "stop_paper"
          : version.status === "paper_paused"
            ? "start_paper"
          : version.status === "analyzed"
            ? "approve"
            : version.status === "execution_validated" && version.execution_validation?.mode === "historical_replay"
              ? "start_paper"
              : "activate");
    const confirmationMessage = action === "validate"
        ? `과거 시세 재생 검사를 실행할까요?\n\n저장된 전략 시간봉과 해당 기관의 완성된 캔들로 규칙·비용·손익·MDD를 계산합니다. 실제 사용 기간과 표본 수는 결과에 표시됩니다. 필요한 시세를 제공하지 않으면 검사를 중단합니다.`
        : action === "start_paper"
          ? version.status === "paper_paused"
            ? "PAPER 검증을 재개할까요?\n\n기존 검증 기간·가상 체결·거래소별 근거를 그대로 이어갑니다. 일시정지 동안의 시간과 신규 거래는 검증 기간에 포함하지 않습니다."
            : `PAPER 전진검증을 시작할까요?\n\n${paperModeEnabled ? "현재 앱은 PAPER 모드입니다." : parallelPaperEnabled ? "현재 앱은 LIVE이며 독립 PAPER 병행검증이 켜져 있습니다." : "현재 앱은 LIVE이며 독립 PAPER 병행검증이 꺼져 있어 등록 후 대기합니다."} 이 버전에는 실주문 권한이 없으며 새 가상 거래만 집계합니다.`
          : action === "restart_paper"
            ? "새 PAPER 검증을 시작할까요?\n\n현재 검증 근거를 이전 시도로 보관하고 0일부터 시작합니다. 기존 원장과 이전 시도는 삭제되지 않습니다."
          : action === "activate"
            ? "이 전략을 최종 적용할까요?\n\nPAPER/실행검증 결과와 적용 범위를 확인하세요. LIVE에서는 별도 계좌 권한과 하드 가드레일이 계속 적용됩니다."
            : action === "approve"
              ? `이 전략 버전을 사용자 승인할까요?\n\n${replayApplicable ? "구조화된 사용자 진입·청산 규칙을 검증합니다." : "NoahAI가 기본 진입을 판단하고 사용자 위험·청산값을 적용합니다. 원문 전체 진입 전략을 실행·검증하는 방식이 아님을 확인하세요."}\n승인은 다음 단계 권한만 열며 PAPER·LIVE는 별도로 시작합니다.`
              : action === "stop_paper"
                ? "PAPER 검증을 일시정지할까요?\n\n검증 기간·가상 체결·거래소별 근거는 보존됩니다."
                : action === "deactivate"
                  ? "이 전략 적용을 해제할까요?\n\n신규 진입 풀에서 제거되며 기존 거래 원장은 보존됩니다."
                  : "이 작업을 실행할까요?";
    if (!window.confirm(confirmationMessage)) return;
    setBusy(true);
    try {
      let updatedVersion: Record<string, unknown> | null = null;
      if (action === "validate") {
        const validationSource = service === "stock" ? source : (targetScope === "binance" ? "binance" : source);
        const validationMarketType = service === "stock" ? undefined : ["upbit", "bithumb", "coinone"].includes(validationSource) ? "spot" : "futures";
        updatedVersion = await client.runHistoricalValidation({
          scope: targetScope,
          strategy_key: version.strategy_key,
          version_id: version.version_id,
          asset_class: service === "stock" ? "stock" : "crypto",
          source: validationSource,
          market_type: validationMarketType,
          symbol: service === "stock" ? "005930" : ["upbit", "bithumb", "coinone"].includes(validationSource) ? "BTCKRW" : "BTCUSDT",
          limit: 500,
        });
        setMessage(`과거 시세 재생 검사 완료 · ${validationSource.toUpperCase()} ${validationMarketType ?? "현물"} 실제 시세로 PnL·MDD·비용을 계산했습니다. 이제 PAPER 전진검증을 시작하세요.`);
      } else {
        updatedVersion = await client.strategyAction({
          scope: targetScope,
          strategy_key: version.strategy_key,
          version_id: version.version_id,
          action,
          live_confirmation: action === "activate",
          operation_mode: "standard",
        });
        setMessage(action === "start_paper"
          ? version.status === "paper_paused"
            ? "PAPER 전진검증을 재개했습니다. 기존 근거와 누적 활성 검증시간을 이어갑니다."
            : `PAPER 전진검증 등록 완료 · ${paperModeEnabled ? "현재 전체 PAPER 모드에서" : parallelPaperEnabled ? "현재 LIVE 옆의 독립 PAPER 엔진에서" : "병행검증이 꺼져 있어 다음 PAPER 모드 또는 병행검증 활성화 후"} 이 전략으로 새로 청산되는 가상 거래만 집계합니다. 최소 3건과 7일 관찰 조건을 화면에서 확인하세요.`
          : action === "restart_paper"
            ? "새 PAPER 검증 시도를 시작했습니다. 이전 근거는 시도 이력과 원장에 보존됩니다."
          : action === "stop_paper"
            ? "PAPER 전진검증을 일시정지했습니다. 검증일수·가상 체결·거래소별 근거는 보존되며 재개할 수 있습니다."
            : `${actionLabel(version)} 완료 · 상태머신과 감사 원장에 기록했습니다.`);
      }
      if (
        updatedVersion
        && guidedVersion?.strategy_key === version.strategy_key
        && guidedVersion?.version_id === version.version_id
      ) {
        setGuidedVersion(updatedVersion as unknown as StrategyVersion);
        if (action === "validate") setGuidedStep(5);
        if (action === "start_paper") {
          finishGuidedTour("5분 따라 만들기를 완료했습니다. PAPER는 실주문 없이 이 전략 버전의 가상 거래 근거를 모읍니다.");
        }
      }
      refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "전략 상태 변경에 실패했습니다.");
      setBusy(false);
    }
  }

  async function remove(targetScope: string, strategyKey: string, versionId?: string) {
    if (!window.confirm(`${versionId ? "이 전략 버전" : "이 전략 전체"}을 삭제할까요?\n\n삭제한 규칙은 복구할 수 없습니다. 적용 중 전략은 서버가 차단하며 거래·검증 감사 식별자는 보존됩니다.`)) return;
    setBusy(true);
    try {
      await client.deleteStrategy(targetScope, strategyKey, versionId);
      setMessage("삭제 완료 · 전략 내용 대신 식별자와 행위자만 감사 기록에 남겼습니다.");
      refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "삭제에 실패했습니다."); setBusy(false); }
  }

  const versionCount = catalog?.strategies.reduce((sum, item) => sum + item.versions.length, 0) ?? 0;
  const versionTargetOptions = useMemo(() => catalog?.strategies
    .filter((group) => group.scope === scope)
    .map((group) => ({
      value: group.strategy_key,
      label: `${group.versions.at(-1)?.name ?? group.strategy_key} · 다음 버전 v${Math.min(10, Number(group.versions.at(-1)?.version ?? 0) + 1)}`,
    })) ?? [], [catalog, scope]);
  const analysisRules = (sourceAnalysis?.rules ?? {}) as Record<string, unknown>;
  const sourceDetails = (sourceAnalysis?.source ?? {}) as Record<string, any>;
  const sourceEvidence = (sourceDetails.evidence ?? {}) as Record<string, any>;
  const sourceTrace = (analysisRules.source_rule_trace ?? {}) as Record<string, any>;
  const missingConditions = Array.isArray(sourceAnalysis?.missing_conditions) ? sourceAnalysis.missing_conditions : [];
  const analysisBlockingDetails = Array.isArray(sourceAnalysis?.blocking_details) ? sourceAnalysis.blocking_details : [];
  const analysisWarnings = Array.isArray(sourceDetails.warnings) ? sourceDetails.warnings : [];
  const analysisRisks = Array.isArray(sourceAnalysis?.risks) ? sourceAnalysis.risks : [];
  const analysisScenarios = Array.isArray(sourceAnalysis?.scenarios) ? sourceAnalysis.scenarios : [];
  const regimeSuggestion = (sourceAnalysis?.market_regime_suggestion ?? {}) as Record<string, any>;
  const analysisReadiness = (sourceAnalysis?.execution_readiness ?? {}) as Record<string, any>;
  const analysisReady = sourceAnalysis?.ready_for_execution === true;
  const guidedBlockingDetails: Array<Record<string, string>> = analysisBlockingDetails.length
    ? analysisBlockingDetails
    : missingConditions.map((item: unknown) => ({
        code: readableDetail(item),
        title: readableDetail(item),
        action: "원문에 해당 조건을 숫자와 단위로 명시한 뒤 다시 분석하세요.",
        example: "진입·청산·손절·익절·거래 위험 조건을 각각 완전한 문장으로 작성",
      }));
  const clarificationQuestions: Array<Record<string, any>> = Array.isArray(sourceAnalysis?.clarification_questions)
    ? sourceAnalysis.clarification_questions
    : guidedBlockingDetails.map((item, index) => ({
        ...item,
        id: `clarification-${index + 1}`,
        question: item.action,
        why: item.explanation,
        resolution: String(item.code || "").startsWith("missing_required_rule:") ? "user_answer" : "source_rewrite",
        auto_executable: false,
      }));
  const answerableClarifications = clarificationQuestions.filter((item) => String(item.resolution || "") === "user_answer");
  const hasClarificationAnswer = clarificationQuestions.some((item, index) =>
    String(item.resolution || "") === "user_answer"
    && Boolean(String(clarificationAnswers[clarificationKey(item, index)] || "").trim()),
  );
  const regimeSuggestionText = sourceAnalysis
    ? regimeSuggestion.auto_select === true
      ? `자료에 명시된 국면: ${marketRegimeLabels(normalizeMarketRegimes(regimeSuggestion.regimes)).join(" · ")} · ${String(regimeSuggestion.evidence ?? "원문 근거 확인")}`
      : "자료에 상승장·하락장·횡보장 같은 명시 근거가 없어 NoahAI 판단을 유지합니다. LONG/SHORT나 이동평균 방향만으로 시장국면을 지어내지 않습니다."
    : "자료를 분석하면 명시된 시장국면만 추천합니다.";
  const saveDisabledReason = busy
    ? "현재 분석 또는 저장 작업이 끝날 때까지 기다리세요."
    : !name.trim()
      ? "전략 버전 이름을 입력하세요."
      : !sourceAnalysis
      ? "먼저 AI 분석 및 전략 초안 만들기를 실행하세요."
        : "";
  const guidedMethodCopy = guidedMethod ? GUIDED_METHOD_COPY[guidedMethod] : null;
  const guidedFrequencyLabel = guidedAnswers.tradeFrequency === "low" ? "낮음" : guidedAnswers.tradeFrequency === "high" ? "높음" : "보통";
  const guidedHistoricalReplayApplicable = guidedVersion ? historicalReplayApplicable(guidedVersion) : true;
  const allCompatibleTarget = service === "stock" ? "asset:stock" : "asset:crypto";
  const compatibleVenueProfiles = venueProfilesForService(service).filter((profile) => profile.paper_supported);
  const analysisAssistantPrompt = sourceAnalysis
    ? strategyExplanationPrompt(sourceAnalysis, name, service)
    : "전략 스튜디오 XAI 결과 화면에서 분석 전 무엇을 입력하고 무엇을 확인해야 하는지 설명해줘.";
  return <section className="legacy-strategy-workspace">
    <header className="legacy-strategy-header">
      <h2>{t("NoahAI 전략 스튜디오")}</h2>
      <p className="strategy-studio-alias">{t("Strategy Studio · 기존 AI 커스텀")}</p>
      <p>{t("TradingView·Pine·기존 전략의 익숙한 표현은 유지하고, 원문 근거·검증·PAPER·체결 감사를 더하는 AI 전략 운영체제입니다. 배우기 → 만들기 → 검증 → 실행 → 개선 흐름을 연결합니다.")}</p>
      <div className="legacy-strategy-status"><strong>{t("사용 AI 및 정밀 분석 역할은 설정의 AI 엔진/API를 따릅니다.")}</strong><span>{t("사용 모드: ")}{strategyDifficultyLabel(featureProfile)}</span><small>{t("설정 경로: AI 엔진/API → 전략 스튜디오 사용 난이도")}</small><button className={`guided-start ${guidedCompletedOnce ? "revisit" : "first"}`} type="button" onClick={openGuidedTour}>{guidedCompletedOnce ? "5분 따라 만들기 다시 보기" : t("처음 사용 · 5분 따라 만들기")}</button><button className="mentor" type="button" onClick={() => setMentorOpen((current) => !current)}>{t("AI 멘토 인터뷰")}</button><button className="getting-started" type="button" onClick={() => onAskAssistant?.("전략 스튜디오를 처음부터 PAPER까지 사용하는 순서를 현재 설정 기준으로 안내해줘.")}>{t("처음 사용법 AI에게 묻기")}</button><a className="strategy-hub-link" href={STRATEGY_HUB_URL} target="_blank" rel="noreferrer" title={t("로그인 없이 공개 전략과 검증 여권을 둘러봅니다.")}>{t("전략 둘러보기")}</a><a className="strategy-hub-link" href={STRATEGY_HUB_LIBRARY_URL} target="_blank" rel="noreferrer" title={t("daltrading 로그인 후 취득한 전략과 라이선스를 확인합니다.")}>{t("내 전략 라이선스")}</a><a className="strategy-hub-link" href={STRATEGY_HUB_GUIDE_URL} target="_blank" rel="noreferrer">{t("제출·다운로드 안내")}</a><button type="button" onClick={onOpenSettings}>{t("AI 모델 설정 열기")}</button></div>
      <details className="strategy-help-difference"><summary>{t("두 도움 기능의 차이")}</summary><p>{t("AI 멘토 인터뷰는 투자 경험·목표·위험 허용도 등 8문항을 묻고 관리형 전략 후보 2~3개를 만듭니다. 실행 계약을 통과한 후보도 자동 저장·승인·PAPER·LIVE로 넘어가지 않습니다.")}<br />{t("처음 사용법 AI에게 묻기는 현재 화면과 프로필을 기준으로 입력 → XAI 검토 → 저장 → 승인 → 적용 가능한 과거검증 → PAPER 순서만 안내합니다.")}</p></details>
      <div className="legacy-strategy-badges"><div><span>{t("승인 없는 실행")}</span><b className="negative">{t("차단")}</b></div><div><span>{t("전략 버전")}</span><b>{t("최대 10개")}</b></div><div><span>{t("가드레일")}</span><b className="positive">{t("항상 우선")}</b></div><div><span>{t("출금 API")}</span><b className="warning">{t("지원 안 함")}</b></div></div>
      {guidedOpen && <div className="strategy-guided-backdrop" role="presentation"><article className="strategy-guided-dialog" role="dialog" aria-modal="true" aria-labelledby="strategy-guided-title">
        <header><div><span>{t("LEVEL 독립 안내 기능")}</span><h3 id="strategy-guided-title">{t("처음 사용 · 5분 따라 만들기")}</h3><p>{t("현재 Level ")}{featureViewLevel}{t("을 그대로 유지합니다. 따라하기는 설정·거래·가드레일을 자동 변경하지 않습니다.")}</p></div><button type="button" aria-label={t("5분 따라 만들기 닫기")} onClick={() => setGuidedOpen(false)}>{t("닫기")}</button></header>
        <ol className="strategy-guided-progress">{GUIDED_STEP_LABELS.map((label, index) => <li className={guidedStep === index + 1 ? "current" : guidedStep > index + 1 ? "complete" : ""} key={label}><b>{index + 1}</b><span>{label}</span></li>)}</ol>
        <section className="strategy-guided-body">
          {guidedStep === 1 && <><div className="strategy-guided-copy"><h4>{t("어떻게 시작할까요?")}</h4><p>{t("어떤 경로도 자동 저장·승인·PAPER·LIVE로 넘어가지 않습니다.")}</p></div><div className="strategy-guided-methods">{(Object.keys(GUIDED_METHOD_COPY) as Array<Exclude<GuidedStartMethod, "">>).map((key) => <button type="button" key={key} onClick={() => chooseGuidedMethod(key)}><strong>{GUIDED_METHOD_COPY[key].title}</strong><span>{GUIDED_METHOD_COPY[key].description}</span></button>)}</div></>}
          {guidedStep === 2 && <><div className="strategy-guided-copy"><h4>{t("쉬운 질문 ")}{guidedQuestion + 1}/3</h4><p>{t("답변은 이번 초안의 검토 기준일 뿐 계좌 설정을 자동 변경하지 않습니다.")}</p></div>
            {guidedQuestion === 0 && <div className="strategy-guided-question"><strong>{t("어떤 자산의 전략을 만들고 있나요?")}</strong><button type="button" className="selected">{t("현재 탭 · ")}{service === "stock" ? t("주식·ETF") : t("암호화폐")}</button><small>{t("다른 자산이라면 따라하기를 닫고 상단에서 블록체인 또는 주식/증권 탭을 먼저 바꾸세요.")}</small></div>}
            {guidedQuestion === 1 && <div className="strategy-guided-question"><strong>{t("원하는 거래 빈도는 어느 정도인가요?")}</strong><div>{[["low", "낮음"], ["medium", "보통"], ["high", "높음"]].map(([value, label]) => <button type="button" className={guidedAnswers.tradeFrequency === value ? "selected" : ""} aria-pressed={guidedAnswers.tradeFrequency === value} key={value} onClick={() => setGuidedAnswers((current) => ({ ...current, tradeFrequency: value }))}>{label}</button>)}</div><small>{t("빈도가 높을수록 거래 기회뿐 아니라 비용과 잘못된 신호 가능성도 늘 수 있습니다.")}</small></div>}
            {guidedQuestion === 2 && <div className="strategy-guided-question"><strong>{t("한 거래에서 검토할 최대 계좌 손실률은?")}</strong><div>{[0.25, 0.5, 1.0].map((value) => <button type="button" className={guidedAnswers.maxLossPercent === value ? "selected" : ""} aria-pressed={guidedAnswers.maxLossPercent === value} key={value} onClick={() => setGuidedAnswers((current) => ({ ...current, maxLossPercent: value }))}>{value}%</button>)}</div><small>{t("전략 요청값이며 실제 주문은 계좌 마스터 상한·시장·성과·거래소 규격에 따라 더 작아질 수 있습니다.")}</small></div>}
            <div className="strategy-guided-actions"><button type="button" onClick={() => guidedQuestion === 0 ? setGuidedStep(1) : setGuidedQuestion((current) => current - 1)}>{t("이전")}</button><button className="primary-button" type="button" onClick={advanceGuidedQuestion}>{guidedQuestion === 2 ? "설명 확인" : "다음 질문"}</button></div></>}
          {guidedStep === 3 && guidedMethodCopy && <><div className="strategy-guided-copy"><h4>{guidedMethodCopy.title}</h4><p>{guidedMethodCopy.description}</p></div><dl className="strategy-guided-summary"><div><dt>{t("현재 Level")}</dt><dd>Level {featureViewLevel}{t(" · 변경 없음")}</dd></div><div><dt>{t("자산")}</dt><dd>{service === "stock" ? t("주식·ETF") : t("암호화폐")}</dd></div><div><dt>{t("선호 빈도")}</dt><dd>{guidedFrequencyLabel}</dd></div><div><dt>{t("검토 위험")}</dt><dd>{t("거래당 최대 ")}{guidedAnswers.maxLossPercent}%</dd></div></dl><div className="strategy-guided-plain"><b>{t("다음에 확인할 내용")}</b><span>{guidedMethod === "noah" ? "NoahAI가 시장과 후보를 판단하고 조건 충돌 시 HOLD합니다. 이 경로는 커스텀 전략 생성 과정이 없으며 바로 완료할 수 있습니다." : guidedMethod === "example" ? "관리형 예제의 진입·청산·거래 금지 조건을 쉬운 설명과 실행 규칙으로 함께 확인합니다." : "가져온 원문에서 진입·청산·TP/SL·시장국면이 확인되는지 분석하고 모르는 조건은 실행하지 않습니다."}</span></div><div className="strategy-guided-actions"><button type="button" onClick={() => setGuidedStep(2)}>{t("이전")}</button>{guidedMethod === "noah" ? <><button type="button" disabled={busy} onClick={() => void prepareGuidedDraft("example")}>{t("전략도 만들기 · 관리형 예제로 전환")}</button><button className="primary-button" type="button" onClick={() => finishGuidedTour("기본 NoahAI 운용 경로를 확인했습니다. 커스텀 전략을 만들거나 적용하지 않았습니다.")}>{t("기본 NoahAI 사용 확인 완료")}</button></> : <button className="primary-button" disabled={busy} type="button" onClick={() => void prepareGuidedDraft()}>{guidedMethod === "example" ? "관리형 예제 불러오기" : "내 전략 입력하기"}</button>}</div></>}
          {guidedStep === 4 && <><div className="strategy-guided-copy"><h4>{t("안전한 전략 버전 만들기")}</h4><p>{t("분석·저장·승인을 각각 확인합니다. 현재 필요한 동작 하나만 아래에 표시합니다.")}</p></div>
            {guidedMethod === "import" && !sourceAnalysis && <div className="strategy-guided-import"><label>{t("전략 설명 또는 Pine Script")}<textarea value={sourceValue} onChange={(event) => { setSourceValue(event.target.value); setSourceFile(null); setSourceReferenceInput(""); setSourceReference(""); setSourceSummary(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }} placeholder={t("예: EMA200 위에서 RSI 30 이하 LONG, 손절 1%, 익절 2%")} /></label><label className="secondary-button">{t("문서·Pine·이미지·영상 파일 선택")}<input type="file" accept=".md,.pdf,.pine,.txt,image/*,video/*" onChange={(event) => { const nextFile = event.target.files?.[0] ?? null; setSourceFile(nextFile); setSourceReferenceInput(nextFile?.name ?? ""); setSourceValue(""); setSourceReference(""); setSourceSummary(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }} /></label>{sourceFile && <small>{t("선택 파일: ")}{sourceFile.name}</small>}</div>}
            <div className="strategy-guided-checks"><div className={sourceAnalysis ? "done" : "current"}><b>1</b><span>{t("원문 분석과 실행 조건 확인")}</span></div><div className={guidedVersion ? "done" : sourceAnalysis ? "current" : ""}><b>2</b><span>{t("최종 재검증 후 비활성 버전 저장")}</span></div><div className={guidedVersion && guidedVersion.status !== "analyzed" ? "done" : guidedVersion ? "current" : ""}><b>3</b><span>{t("사용자 승인")}</span></div><div className={guidedVersion && !["analyzed", "approved", "execution_rejected"].includes(guidedVersion.status) ? "done" : guidedVersion && ["approved", "execution_rejected"].includes(guidedVersion.status) ? "current" : ""}><b>4</b><span>{guidedHistoricalReplayApplicable ? "과거 시세 재생 검사" : "과거재생 비대상 확인"}</span></div></div>
            {busy && <div className="strategy-guided-processing" role="status"><strong>{t("원문과 실행 규칙을 대조하고 있습니다.")}</strong><span>{t("Pine·문서·영상 또는 외부 AI 정밀 분석은 1분 이상 걸릴 수 있습니다. 창을 닫아도 분석은 취소되지 않으며 완료 후 현재 초안에 반영됩니다.")}</span></div>}
            {sourceAnalysis && <div className={`strategy-guided-readiness ${analysisReady ? "ready" : "blocked"}`}><strong>{analysisReady ? "실행 규칙 구조화 완료" : `보완할 조건 ${guidedBlockingDetails.length || 1}개`}</strong><span>{analysisReady ? "저장 전 최종 재검증을 한 번 더 수행합니다." : "아래 조건을 원문에서 고친 뒤 다시 분석해야 합니다. 모르는 조건을 추측해서 저장하지 않습니다."}</span></div>}
            {guidedVersion && ["approved", "execution_rejected"].includes(guidedVersion.status) && !guidedHistoricalReplayApplicable && <div className="strategy-guided-plain"><b>{t("이 전략은 독립 과거재생 대상이 아닙니다.")}</b><span>{t("NoahAI가 진입 후보를 만들고 이 버전은 사용자 위험·청산 규칙을 적용합니다. 진입 규칙을 임의로 만들어 과거 성과를 표시하지 않고, 다음 PAPER 단계에서 실제 NoahAI 후보와 함께 전진검증합니다.")}</span></div>}
            {sourceAnalysis && !analysisReady && <div className="strategy-guided-fix-panel"><h5>{t("무엇을 고쳐야 하나요?")}</h5><ol>{guidedBlockingDetails.map((item, index) => <li key={`${item.code}:${index}`}><strong>{index + 1}. {item.title || item.code}</strong><span>{item.action || "원문 조건을 구체적으로 작성하세요."}</span>{item.example && <small>{t("입력 예시: ")}{item.example}</small>}{canInsertConfirmedSupplement(item.code) && <button type="button" onClick={() => void insertConfirmedSupplement(item.code)}>{t("화면 선택값을 보완 근거로 확정·재분석")}</button>}</li>)}</ol>{sourceFile ? <div className="strategy-guided-file-fix"><b>{t("파일 원문은 앱에서 덮어쓰지 않습니다.")}</b><span>{t("창을 닫으면 아래 본 화면의 「질문으로 함께 완성」에서 자신의 답변을 별도 근거로 추가할 수 있습니다. 지원하지 않는 Pine 동작은 원본을 수정해야 하며 AI가 비슷한 조건으로 바꾸지 않습니다.")}</span></div> : <label className="strategy-guided-source-fix">{t("수정할 원문")}<textarea value={sourceValue} onChange={(event) => { setSourceValue(event.target.value); setSourceAnalysis(null); setDraftValidationIssues([]); setConfirmedSupplement(""); setClarificationAnswers({}); setMessage("원문을 수정했습니다. 다시 분석해 변경된 조건을 확인하세요."); }} /></label>}<div className="strategy-guided-fix-actions">{onAskAssistant && <button type="button" onClick={() => onAskAssistant(`전략 스튜디오 최종 재검증에서 다음 항목이 차단됐어. 초보자가 원문을 어떻게 고치면 되는지 순서와 예시로 설명해줘: ${guidedBlockingDetails.map((item) => `${item.title} (${item.code})`).join(", ")}`)}>{t("이 조건을 AI에게 묻기")}</button>}<button type="button" onClick={() => { setGuidedOpen(false); setAuthoringMode("guided_clarification"); setMessage("본 화면의 질문 카드에서 답을 입력하거나 원문을 수정한 뒤 다시 분석하세요."); }}>{t("원문 다시 분석 준비 · 질문에 답하기")}</button></div></div>}
            <div className="strategy-guided-actions"><button type="button" onClick={() => setGuidedStep(3)}>{t("이전")}</button>{!sourceAnalysis ? <button className="primary-button" disabled={busy || (!sourceFile && !sourceReferenceInput.trim() && !sourceValue.trim())} type="button" onClick={() => void analyzeSource()}>{busy ? "분석 중…" : t("AI 분석 및 전략 초안 만들기")}</button> : !guidedVersion ? <button className="primary-button" disabled={busy || !analysisReady} type="button" onClick={() => void createStrategy()}>{busy ? "재검증 중…" : t("최종 재검증 후 전략 버전 저장")}</button> : guidedVersion.status === "analyzed" ? <button className="primary-button" disabled={busy} type="button" onClick={() => void runAction(guidedVersion, scope)}>{t("사용자 승인")}</button> : ["approved", "execution_rejected"].includes(guidedVersion.status) && guidedHistoricalReplayApplicable ? <button className="primary-button" disabled={busy} type="button" onClick={() => void runAction(guidedVersion, scope)}>{guidedVersion.status === "execution_rejected" ? "과거 시세 재생 다시 검사" : "과거 시세 재생 검사"}</button> : <button className="primary-button" type="button" onClick={() => setGuidedStep(5)}>{t("PAPER 단계로 이동")}</button>}</div>
            {draftValidationIssues.length > 0 && <div className="strategy-guided-warning"><strong>{t("저장 전 확인 필요")}</strong><span>{draftValidationIssues.map((item) => item.title || item.code).join(" · ")}</span><button type="button" onClick={showRepairInstructions}>{t("고칠 항목으로 이동")}</button></div>}
          </>}
          {guidedStep === 5 && <><div className="strategy-guided-copy"><h4>{guidedCompleted ? "따라 만들기 완료" : t("PAPER 전진검증 시작")}</h4><p>{guidedCompleted ? "언제든 다시 열어 같은 흐름을 연습할 수 있습니다." : "PAPER는 실주문 권한 없이 시장 시세로 가상 포지션과 거래 근거를 기록합니다."}</p></div>{guidedCompleted ? <div className="strategy-guided-complete"><strong>{guidedVersion ? `${guidedVersion.name} · PAPER 등록 확인` : "기본 NoahAI 운용 경로 확인"}</strong><span>Level {featureViewLevel}{t(", 계좌 설정, 저장된 전략과 기존 PAPER 원장은 변경하거나 삭제하지 않았습니다.")}</span></div> : <><div className="strategy-guided-plain"><b>{t("시작 전 확인")}</b><span>{t("검증 통과가 자동 LIVE 적용으로 이어지지 않습니다. 최소 거래 수와 활성 검증기간을 채운 뒤에도 사용자가 최종 적용을 별도로 승인해야 합니다.")}</span></div>{!paperModeEnabled && !parallelPaperEnabled && <div className="strategy-guided-warning"><strong>{t("현재 PAPER 실행 대기 상태")}</strong><span>{t("전체 PAPER 모드 또는 LIVE 중 독립 PAPER 병행검증을 먼저 켜야 새 가상 거래가 집계됩니다.")}</span><button type="button" onClick={onOpenSettings}>{t("PAPER 설정 열기")}</button></div>}<div className="strategy-guided-actions"><button type="button" onClick={() => setGuidedStep(4)}>{t("이전")}</button><button className="primary-button" disabled={busy || !guidedVersion || guidedVersion.paper_execution_readiness?.ready === false} type="button" onClick={() => guidedVersion && void runAction(guidedVersion, scope, "start_paper")}>{t("PAPER 전진검증 시작")}</button></div></>}</>}
        </section>
        <footer><button type="button" onClick={restartGuidedTour}>{t("따라하기 안내 초기화")}</button><span>{t("안내 초기화는 저장 전략·PAPER·거래·학습 데이터를 삭제하지 않습니다.")}</span><button type="button" onClick={() => setGuidedOpen(false)}>{t("닫기")}</button></footer>
      </article></div>}
      {mentorOpen && <article className="strategy-mentor-panel"><header><div><h3>{t("AI 멘토 구조화 인터뷰")}</h3><p>{t("답변은 로컬 전략 후보 추천에만 사용되며 자동 저장·승인·적용되지 않습니다.")}</p></div><button type="button" onClick={() => setMentorOpen(false)}>{t("닫기")}</button></header><div className="strategy-mentor-grid">{MENTOR_FIELDS.map((field) => <label key={field.key}>{field.label}<select value={String(mentorProfile[field.key] ?? "")} onChange={(event) => { const raw = event.target.value; setMentorProfile((current) => ({ ...current, [field.key]: raw === "true" ? true : raw === "false" ? false : raw })); }}>{field.options.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}<label>{t("거래당 최대 허용 손실률")}<input type="number" min="0.05" max="5" step="0.05" value={String(mentorProfile.max_loss_percent ?? 0.5)} onChange={(event) => setMentorProfile((current) => ({ ...current, max_loss_percent: Number(event.target.value) }))} /><span>%</span></label></div><button className="primary-button" type="button" disabled={busy} onClick={() => void runMentor()}>{t("검토 후보 2~3개 만들기")}</button>{mentorCandidates.length > 0 && <div className="strategy-mentor-candidates">{mentorCandidates.map((candidate) => <section key={String(candidate.preset_key)}><h4>{String(candidate.name)}</h4><p>{String(candidate.summary)}</p><small>{String(candidate.why_fit)}{t(" · 거래하지 않을 때: ")}{String(candidate.when_not_to_trade)}</small><small>{candidate.executable_template === true ? "실행 규칙 구조화 완료 · 저장 전 검토 필요" : "교육용 후보 · 실행 조건 보완 필요"} · {String(candidate.venue_note ?? "거래소 능력에 따라 실행 방향이 제한됩니다.")}</small><button type="button" onClick={() => loadMentorCandidate(candidate)}>{t("이 후보를 입력 영역에 불러오기")}</button></section>)}</div>}</article>}
      <div className="legacy-strategy-feature-location"><div><b>{t("전략 스튜디오 기능 위치 · 현재 선택: ")}{resultView}</b><button type="button" onClick={() => setShowLevelGuide((current) => !current)}>{showLevelGuide ? "Level 비교 닫기" : t("Level 1~4 비교·예시")}</button></div><p>{t("Level은 수익률·전략 품질·회원 등급이 아니라 화면 설명 깊이와 편집·운용 범위입니다. 단계를 바꿔도 전략이 자동 수정되거나 실행되지 않습니다.")}</p></div>
      {showLevelGuide && <article className="legacy-level-guide" aria-label={t("전략 스튜디오 Level 1부터 Level 4 비교")}><header><div><h3>{t("Level 1~4 이용 범위와 예시")}</h3><p>{t("앱에 포함된 로컬 안내이므로 열어보는 데 AI API 비용이 들지 않습니다.")}</p></div><button type="button" onClick={onOpenDifficultySettings ?? onOpenSettings}>{t("사용 난이도 설정")}</button></header><div>{LEVEL_GUIDE.map((item) => <section className={featureViewLevel === item.level ? "current" : ""} key={item.level}><span>{strategyDifficultyLabel(["beginner", "standard", "advanced", "lab"][item.level - 1])}</span><h4>{t(item.profile)}</h4><p><b>{t("할 수 있는 것")}</b>{item.canDo}</p><p><b>{t("예시")}</b>{item.scenario}</p>{featureViewLevel === item.level && <small>{t("현재 설정에서 기본으로 열리는 단계")}</small>}</section>)}</div><footer>{t("TradingView·Pine 사용자는 보통 Level 2에서 실제 적용값을 먼저 확인한 뒤, 직접 규칙을 수정할 때만 Level 3으로 올리는 것이 안전합니다. Level 4는 하드 가드레일 해제 기능이 아닙니다.")}</footer></article>}
      <div className="legacy-strategy-safe"><div><b>{t("안전 사용 순서")}</b><span>{t("AI 설정·엔진 ON → 멘토/자료 입력 → 권장 역할·XAI/규칙 확인 → 버전 저장·승인·과거 재생 또는 비대상 확인 → PAPER → 제한 LIVE")}</span></div><button type="button" onClick={() => setShowSafeSteps((current) => !current)}>{showSafeSteps ? "12단계 닫기" : t("12단계 자세히 · API 비용 없음")}</button></div>
      <div className={`strategy-paper-mode-notice ${paperModeEnabled || parallelPaperEnabled ? "paper" : "live"}`}><strong>{paperModeEnabled ? "현재 전체 PAPER 모드 · 전진검증 집계 가능" : parallelPaperEnabled ? "현재 LIVE · 독립 PAPER 병행검증 가능" : "현재 LIVE · 독립 PAPER 병행검증 꺼짐"}</strong><span>{paperModeEnabled ? "전체 PAPER는 거래소별 가상 실행 슬롯에서 전략 조건에 맞는 새 가상 청산과 관찰 시간을 집계합니다." : parallelPaperEnabled ? "병행 PAPER는 LIVE 시세만 공유하고 전략·버전·거래소별 가상자금·포지션·원장을 분리합니다. 거래소 주문 API를 소유하지 않으며 검증 통과도 자동 LIVE 적용되지 않습니다." : "전략을 검증 풀에 등록해도 현재는 대기합니다. 전체 PAPER로 전환하거나 설정에서 독립 PAPER 병행검증을 켜야 새 가상 청산과 관찰 시간이 증가합니다."}</span><button type="button" onClick={onOpenSettings}>{t("PAPER/LIVE 설정 열기")}</button></div>
      <article className="strategy-venue-compatibility" aria-label={t("현재 전략 실행 범위와 거래소 호환성")}>
        <header><b>{t("실행 전 기관·상품 호환성")}</b><span>{executionTargetLabel(service, executionTarget)}</span></header>
        <ul>{venueCompatibilityText(service, executionTarget, source).map((item) => <li key={item}>{item}</li>)}</ul>
        <p>{t("지원되지 않는 SHORT·시장 유형·주문 규격은 전략 의미를 바꾸어 실행하지 않고 해당 거래소에서 차단합니다. 다른 거래소의 성공 결과를 현재 거래소 성과로 합산하지 않습니다.")}</p>
      </article>
      {showSafeSteps && <article className="legacy-safe-steps" aria-label={t("전략 스튜디오 12단계 안전 사용 순서")}><h3>{t("전략 스튜디오 12단계 안전 사용 순서")}</h3><p>{t("이 안내는 앱에 포함된 로컬 정본이며 외부 AI API를 호출하지 않습니다.")}</p><ol>{SAFE_USE_STEPS.map((step, index) => <li key={step}><b>{String(index + 1).padStart(2, "0")}</b><span>{step}</span></li>)}</ol></article>}
    </header>
    <article className="legacy-beginner-presets">
      <div><h2>{t("초보자 시작: AI 자동 대응 + 검토용 기본 전략 4개")}</h2><span /><button className="preset-explain" type="button" onClick={() => onAskAssistant?.(`${BEGINNER_PRESETS.find((item) => item.key === beginnerPreset)?.label ?? "AI 자동 대응"} 전략의 적합한 시장 국면, 위험, HOLD 조건을 초보자에게 설명해줘.`)}>{t("AI에게 설명 듣기")}</button><button type="button" onClick={loadBeginnerPreset}>{beginnerPreset === "auto_regime" ? t("기본 NoahAI 사용 확인") : "선택 내용 불러오기"}</button><select value={beginnerPreset} onChange={(event) => setBeginnerPreset(event.target.value)}>{BEGINNER_PRESETS.map((preset) => <option key={preset.key} value={preset.key}>{t(preset.label)}</option>)}</select></div>
      <p>{t("기본 선택인 AI 자동 대응은 기존 NoahAI 시장판단입니다. 나머지 4개는 편집 가능한 초안이며 성과를 보장하지 않습니다. 국면·다중 시간대·유동성·손익비가 충돌하면 HOLD가 항상 우선합니다.")}</p>
    </article>
    <article className="legacy-beginner-regime-guide">
      <div><b>{t("시장을 잘 모르겠다면 그대로 두세요")}</b><span>{t("「NoahAI 판단 + 기본 AI 후보 확인」이 초보자 권장값입니다. NoahAI가 시장과 후보 방향을 먼저 판단하고, 가져온 전략은 조건이 맞는지만 한 번 더 확인합니다.")}</span></div>
      <ul><li>{t("자료에 “상승장에서만”처럼 명시돼 있으면 해당 국면만 자동 추천합니다.")}</li><li>{t("상승·하락·횡보 규칙이 서로 다르면 전략을 각각 저장해 현재 국면에 맞는 한 전략을 선택하게 합니다.")}</li><li>{t("이동평균 LONG 전략만으로 하락·횡보용 반대 전략을 자동 생성하지 않습니다.")}</li><li>{t("커스텀 조건이 맞지 않으면 HOLD입니다. 커스텀을 완전히 빼고 기본 NoahAI만 쓰려면 전략을 적용하지 않거나 적용 해제하세요.")}</li></ul>
    </article>
    <nav className="strategy-step-nav" aria-label={t("전략 작업 단계")}>
      {[[".legacy-strategy-source-card", "1. 전략 입력"], [".legacy-strategy-result-card", "2. 이해·보완"], [".studio-panel", "3. 저장 버전·검증·차트"]].map(([target, label]) => <button type="button" key={target} onClick={(event) => { const root = event.currentTarget.closest(".legacy-strategy-workspace"); const element = root?.querySelector(target) ?? root?.querySelector(".legacy-xai-result"); element?.scrollIntoView({ block: "start", behavior: "smooth" }); }}>{label}</button>)}
    </nav>
    <div className="studio-layout legacy-studio-stack">
    <article className="panel studio-editor legacy-strategy-source-card">
      <div ref={repairRef} tabIndex={-1} className={repairVisible ? "strategy-repair-focus" : ""}>
        {repairVisible && <><strong>{t("여기서 원문과 확인 답변을 고칩니다")}</strong><ol><li>{t("아래 입력 영역에서 원문 또는 보완 답변을 수정하세요.")}</li><li>{t("「AI 분석 및 전략 초안 만들기」를 누르세요.")}</li><li>{t("확인 항목이 해결되면 「최종 재검증 후 전략 버전 저장」을 누르고 따라 만들기를 다시 여세요.")}</li></ol>{draftValidationIssues.map((item, i) => <p key={i}><b>{item.title}</b> · {item.action}{item.example ? ` 예: ${item.example}` : ""}</p>)}</>}
      </div>
      <div className="strategy-validation-settings"><label>{t("전략 판단 시간봉 ")}<select value={decisionTimeframe} onChange={(event) => { setDecisionTimeframe(event.target.value); try { const rules = JSON.parse(rulesText); setRulesText(JSON.stringify({ ...rules, decision_timeframe: event.target.value, execution_timeframe: event.target.value }, null, 2)); } catch { /* JSON editor reports invalid syntax on save */ } }}><option value="">{t("원문 시간봉 선택")}</option>{["1m", "3m", "5m", "15m", "30m", "1h", "4h", "1d"].map(tf => <option key={tf} value={tf}>{tf}</option>)}</select></label><span>{t("원문이 사용하는 시간봉을 확인하세요. 저장된 시간봉으로만 과거 재생하며, 증권사 분봉 공급이 없으면 일봉으로 대체하지 않습니다.")}</span></div>
      <section className="source-ingestor legacy-source-ingestor">
        <StrategyBeginnerHelp />
        <div className="legacy-source-title"><h3>{t("1. 전략 소스 입력")}</h3><div className="legacy-source-title-actions"><button className="secondary-button" type="button" disabled={busy} onClick={resetDraft}>{t("새로 시작 · 입력 초기화")}</button><select value={sourceKind} onChange={(event) => { setSourceKind(event.target.value); setSourceFile(null); setSourceReference(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }}><option value="auto">{t("자동 판별")}</option><option value="text">{t("텍스트/메모")}</option><option value="pine">Pine Script</option><option value="pdf">{t("PDF 문서")}</option><option value="image">{t("차트 이미지/OCR")}</option><option value="video">{t("로컬 영상")}</option><option value="youtube">{t("YouTube 링크")}</option><option value="tradingview">{t("TradingView 링크")}</option></select></div></div>
        {versionTarget && <label className="strategy-version-confirm"><input type="checkbox" checked={userDeclaredOverride} onChange={(event) => setUserDeclaredOverride(event.target.checked)} />{t("기존 규칙에서 변경한 실행값을 확인했습니다. 새 버전으로 저장하며 승인·검증·적용은 다시 진행합니다.")}</label>}
        {versionTarget && <button className="primary-button" type="button" disabled={busy || !userDeclaredOverride} onClick={() => void createStrategy()}>{t("변경값 재검증 후 다음 버전 저장")}</button>}
        <div className="legacy-version-target-row"><span>{t("저장 대상")}</span><select value={versionTarget} onChange={(event) => loadVersionDraft(event.target.value)}><option value="">{t("새 전략으로 저장")}</option>{versionTargetOptions.map((option) => <option key={option.value} value={option.value}>{t(option.label)}</option>)}</select><small>{t("기존 전략을 고르면 같은 전략의 다음 버전(v2~v10)으로 저장됩니다.")}</small></div>
        <section className="strategy-authoring-mode" aria-label={t("전략 만들기 방식")}>
          <header><div><b>{t("어떻게 만들까요?")}</b><span>Level {featureViewLevel}{t("은 그대로 유지되며, 아래 선택은 AI가 전략 의미를 바꿀 수 있는 권한이 아닙니다.")}</span></div></header>
          <div className="strategy-authoring-options">{AUTHORING_MODES.map((mode) => <button className={authoringMode === mode.value ? "selected" : ""} aria-pressed={authoringMode === mode.value} key={mode.value} type="button" onClick={() => { setAuthoringMode(mode.value); setSourceAnalysis(null); setDraftValidationIssues([]); setClarificationAnswers({}); if (mode.value === "noah_delegate") { setSignalMode("confirm"); setEntrySignal("auto"); setExitPolicyMode("inherit_noah_base"); setMarketRegimes(["all"]); } }}><strong>{t(mode.label)}</strong><span>{t(mode.description)}</span></button>)}</div>
          {authoringMode === "guided_clarification" && <p className="strategy-authoring-notice">{t("AI는 질문과 예시만 제공합니다. 예시를 자동 선택하지 않으며, 사용자가 입력하고 확정한 답변만 원본과 분리된 근거로 저장합니다.")}</p>}
          {authoringMode === "noah_delegate" && <div className="strategy-authoring-delegate"><div><b>{t("이 경로는 커스텀 전략을 만들지 않습니다.")}</b><span>{t("기존 입력은 즉시 삭제되지 않습니다. 아래 버튼으로 확정하면 입력 중인 초안만 정리하고 기본 NoahAI 운용 안내로 전환합니다.")}</span></div><button type="button" onClick={() => loadBeginnerPresetByKey("auto_regime")}>{t("기본 NoahAI 사용 확인")}</button></div>}
        </section>
        <div className="legacy-source-path-row"><input value={sourceReferenceInput} onChange={(event) => { setSourceReferenceInput(event.target.value); setSourceFile(null); setSourceReference(""); setSourceSummary(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }} placeholder={t("YouTube/TradingView URL 또는 Markdown·PDF·이미지·영상·Pine 파일 경로")} /><label className="legacy-file-picker">{t("파일 선택")}<input type="file" accept=".md,.pdf,.pine,.txt,image/*,video/*" onChange={(event) => { const nextFile = event.target.files?.[0] ?? null; setSourceFile(nextFile); setSourceReferenceInput(nextFile?.name ?? ""); setSourceValue(""); setSourceReference(""); setSourceSummary(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }} /></label></div>
        <div className="legacy-source-input-label"><b>{t("전략 설명 / Pine Script 직접 입력")}</b><small>{t("예: RSI<30 + EMA200 상단에서 진입, 손절 1%, 익절 2%, 자산 5%")}</small></div>
        <textarea className="source-editor" value={sourceValue} onChange={(event) => { setSourceValue(event.target.value); setSourceFile(null); setSourceReferenceInput(""); setSourceReference(""); setSourceSummary(""); setSourceAnalysis(null); setConfirmedSupplement(""); setClarificationAnswers({}); }} placeholder={t("전략 설명 또는 Pine Script를 붙여 넣으세요. 링크/파일을 선택한 경우 비워도 됩니다.")} />
        {assistantDraftText && <section className="strategy-assistant-draft" ref={assistantDraftPanelRef} aria-live="polite"><header><div><b>{t("AI 답변 검토 · 아직 전략에 적용되지 않음")}</b><span>{t("복사·붙여넣기 없이 가져왔습니다. 틀린 내용이나 AI가 추측한 조건을 지우고, 자신의 전략 기준만 남기세요.")}</span></div></header><textarea value={assistantDraftText} onChange={(event) => setAssistantDraftText(event.target.value)} /><footer><button type="button" onClick={() => { setAssistantDraftText(""); onAssistantDraftConsumed?.(); setMessage("AI 답변 초안을 버렸습니다. 기존 전략 입력과 분석은 유지했습니다."); }}>{t("사용하지 않기")}</button><button className="primary-button" type="button" disabled={busy || !assistantDraftText.trim()} onClick={() => void applyAssistantDraft()}>{t("사용자 보완 근거로 확정·재분석")}</button></footer><small>{t("확정해도 저장·승인·PAPER·LIVE는 자동 실행되지 않습니다. 진입·청산·TP/SL 등은 결정형 컴파일러가 원문 근거를 다시 검사합니다.")}</small></section>}
        {confirmedSupplement && <details className="strategy-confirmed-supplement" open><summary>{t("사용자가 확인한 보완 답변 · 원본과 별도 보관")}</summary><textarea value={confirmedSupplement} onChange={(event) => { setConfirmedSupplement(event.target.value); setSourceAnalysis(null); setDraftValidationIssues([]); }} /><div><span>{t("AI가 만든 실행값이 아닙니다. 파일·Pine·PDF 원본은 덮어쓰지 않으며, 변경 후 다시 분석해야 합니다.")}</span><button type="button" onClick={() => { setConfirmedSupplement(""); setSourceAnalysis(null); setClarificationAnswers({}); setMessage("사용자 확인 보완 답변을 비웠습니다. 원본 전략은 변경하지 않았습니다."); }}>{t("보완 답변 비우기")}</button></div></details>}
        <small className="legacy-analysis-limit">{t("분석 범위: PDF 앞 100쪽·AI 입력 60,000자 / 자막 있는 YouTube는 공개 자막 우선·대표 장면 최대 9개 / 무자막 음성 전사는 기본 최대 45분이면서 24MB 이하(API 사용량 발생 가능) / 보호된 TradingView는 본인 Pine 필요")}</small>
        {featureViewLevel === 1 && <div className="inline-notice">{t("초보자 권장값을 사용합니다: NoahAI 국면 판단 · 기본 AI 후보 확인 · 스마트 청산 상속 · 표준 위험정책. 세부 범위와 숫자를 직접 바꾸려면 설정에서 일반(Level 2) 이상을 선택하세요.")}</div>}
        {featureViewLevel >= 2 && <><div className="legacy-strategy-controls">
          <div>{t("전략 호환 범위")}<fieldset className="venue-checkbox-picker"><legend>{t("거래소·증권사 복수 선택")}</legend><label><input type="checkbox" checked={executionTarget === allCompatibleTarget} onChange={(event) => { if (event.target.checked) changeExecutionTarget(allCompatibleTarget); }} />{t("호환되는 모든 기관")}</label>{compatibleVenueProfiles.map((profile) => {
            const prefix = service === "stock" ? "broker" : "exchange";
            const selected = executionTarget.startsWith(prefix + ":") ? executionTarget.split(":")[1].split(",") : [];
            return <label key={profile.id}><input type="checkbox" checked={selected.includes(profile.client_id)} onChange={(event) => {
              const next = event.target.checked ? [...selected, profile.client_id] : selected.filter((id) => id !== profile.client_id);
              if (!next.length) { setMessage("최소 한 기관을 선택하세요. 전체 범위는 별도로 선택해야 합니다."); return; }
              changeExecutionTarget(prefix + ":" + [...new Set(next)].sort().join(","));
            }} />{profile.display_name} · {profile.quote_currency}</label>;
          })}</fieldset></div>
          {featureViewLevel >= 3 && <label>{t("국면 기준")}<select value={regimeScope} onChange={(event) => setRegimeScope(event.target.value)}><option value="market">{t("전체 시장 기준 (권장)")}</option><option value="symbol">{t("종목별 기준")}</option><option value="both">{t("전체 시장+종목 모두")}</option></select></label>}
          {(featureViewLevel >= 3 || !!versionTarget) && <label>{t("우선순위")}<select value={priority} onChange={(event) => setPriority(event.target.value)}>{[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map((value) => <option key={value}>{value}</option>)}</select></label>}
        </div>
        <fieldset className="legacy-market-regime-picker"><legend>{t("이 전략이 사용할 시장상황")}</legend><div>{MARKET_REGIME_OPTIONS.map((option) => <button key={option.value} type="button" className={marketRegimes.includes(option.value) ? "selected" : ""} aria-pressed={marketRegimes.includes(option.value)} onClick={() => toggleMarketRegime(option.value)}>{t(option.label)}</button>)}</div><small>{t("여러 국면을 직접 고를 수 있습니다. 잘 모르겠으면 첫 번째 권장값을 유지하세요. 소스 분석은 원문에 명시된 국면만 자동 선택합니다.")}</small></fieldset>
        <div className="legacy-signal-controls">
          <label>{t("전략 역할")}<select value={signalMode} onChange={(event) => { const next = event.target.value; setSignalMode(next); if (next === "independent") setExitPolicyMode("strategy_owned"); }}><option value="confirm">{t("기본 AI 후보 확인 (권장)")}</option><option value="independent" disabled={featureViewLevel < 3}>{t("내 전략이 진입 신호 생성 (고급)")}</option></select></label>
          {signalMode === "independent" && <label>{service === "stock" ? "주문 방향" : "진입 방향"}<select value={entrySignal} onChange={(event) => setEntrySignal(event.target.value)}><option value="auto">{t("소스에서 자동")}</option><option value="LONG">{service === "stock" ? t("매수") : "LONG"}</option><option value="SHORT">{service === "stock" ? "보유분 매도" : "SHORT"}</option></select></label>}
          <label>{t("청산 책임")}<select value={signalMode === "independent" ? "strategy_owned" : exitPolicyMode} disabled={signalMode === "independent"} onChange={(event) => setExitPolicyMode(event.target.value)}><option value="inherit_noah_base">{t("NoahAI 스마트 청산 상속 (권장)")}</option><option value="strategy_owned">{t("전략에 적힌 TP/SL 고정")}</option></select></label>
          <small>{signalMode === "confirm" ? t("NoahAI 후보를 한 번 더 확인합니다. 스마트 청산 상속 시 ATR·변동성·성과 기반 기본 정책을 사용합니다.") : "독립 전략은 명시한 진입 방향 또는 LONG/SHORT별 조건과 단위가 명확한 TP/SL이 필요합니다."}</small>
        </div>
        <p className="legacy-strategy-role-help">{t("전략 역할과 실행 안전등급은 주문 환경과 별개입니다. LEARNING은 판단만 기록, PAPER는 가상 체결, LIVE는 명시 허용 범위만 실주문 후보입니다.")}</p>
        {featureViewLevel >= 4 ? <div className={`legacy-risk-controls ${service === "stock" ? "stock" : ""}`}>
          <label>{t("전략 위험예산")}<select value={riskPerTrade} onChange={(event) => { setRiskPerTrade(event.target.value); setRiskPolicyPreset("custom"); }}><option value={"0.25"}>0.25</option><option value={"0.5"}>0.5</option><option value={"1.0"}>1.0</option><option value={"2.0"}>2.0</option></select><span>{t("%/거래")}</span></label>
          <label>{service === "stock" ? "종목당 최대 비중" : "증거금 최대"}<select value={maxMargin} onChange={(event) => { setMaxMargin(event.target.value); setRiskPolicyPreset("custom"); }}><option value={"5"}>5</option><option value={"10"}>10</option><option value={"20"}>20</option><option value={"30"}>30</option></select><span>%</span></label>
          {service === "blockchain" && <label>{t("레버리지 상한")}<select value={leverageCap} onChange={(event) => { setLeverageCap(event.target.value); setRiskPolicyPreset("custom"); }}><option value={"1"}>1</option><option value={"2"}>2</option><option value={"3"}>3</option><option value={"5"}>5</option></select></label>}
          <label>{t("전략 동시 포지션 요청")}<select value={maxConcurrentPositions} onChange={(event) => { setMaxConcurrentPositions(event.target.value); setRiskPolicyPreset("custom"); }}><option value={"1"}>1</option><option value={"2"}>2</option><option value={"3"}>3</option><option value={"5"}>5</option><option value={"10"}>10</option></select><span>{t("개")}</span></label>
          <label>{t("국면 이탈 시")}<select value={conflictFallback} onChange={(event) => { setConflictFallback(event.target.value); setRiskPolicyPreset("custom"); }}><option value={"기본 노아AI에 맡김"}>{t("기본 노아AI에 맡김")}</option><option value={"커스텀 신규 진입 일시정지"}>{t("커스텀 신규 진입 일시정지")}</option></select></label>
        </div> : <div className="inline-notice">{t("위험 운용값은 표준형으로 저장됩니다. 직접 조정은 Level 4 전문가 화면에서만 가능하며, 어떤 값도 계좌 마스터 상한이나 하드 가드레일을 높이지 못합니다.")}</div>}
        <small className="legacy-leverage-note">{service === "stock" ? "주식/ETF는 증권사 현물 주문만 사용하며 레버리지는 1배로 고정됩니다. 매도 신호는 보유 수량을 넘지 않습니다." : t("실제 레버리지는 위험예산÷손절거리로 계산되며 상한을 넘지 않습니다.")}</small>
        </>}
        <div className="legacy-analysis-row"><small>{authoringMode === "noah_delegate" ? "기본 NoahAI 위임은 커스텀 전략을 저장하지 않습니다." : t("범위가 넓어도 거래소·증권사 데이터와 전략 성과는 서로 분리 기록됩니다.")}</small><button className="primary-button legacy-analysis-button" disabled={busy || authoringMode === "noah_delegate" || (!sourceFile && !sourceReferenceInput.trim() && !sourceValue.trim())} onClick={() => void analyzeSource()} type="button">{busy ? "추출·분석 중…" : authoringMode === "guided_clarification" ? "분석하고 보완 질문 받기" : t("AI 분석 및 전략 초안 만들기")}</button></div>
      </section>
    </article>
    <article className="panel studio-editor legacy-strategy-result-card">
      <div className="panel-heading legacy-xai-heading"><div className="legacy-xai-title-group"><h3>{t("2. XAI 분석 결과와 적용값")}</h3><select value={resultView} onChange={(event) => setResultView(event.target.value)}><option value={"Level 1 이해·시험"}>{t("Level 1 이해·시험")}</option><option disabled={featureViewLevel < 2} value={"Level 2 핵심값"}>{t("Level 2 핵심값")}</option><option disabled={featureViewLevel < 3} value="Level 3 전체 근거">{t("Level 3 전체 IR")}</option><option disabled={featureViewLevel < 4} value="Level 4 전문가 운용">{t("Level 4 전문가 운용")}</option></select><small>{featureViewLevel < 3 ? t("Level 3은 설정에서 고급을 선택하면 열립니다.") : featureViewLevel < 4 ? "Level 4는 실험실에서 열리며 가드레일 해제 권한은 없습니다." : "Level 4 전문가 운용 정책을 사용할 수 있습니다."}</small></div><div className="legacy-xai-actions"><button type="button" disabled={!onAskAssistant} onClick={() => onAskAssistant?.(analysisAssistantPrompt)}>{t("이 결과 AI에게 묻기")}</button><span>{sourceAnalysis ? "분석 완료" : t("분석 전")}</span></div></div>
      <div className="legacy-xai-result">{sourceAnalysis ? <><strong>{String(sourceAnalysis.summary ?? "원본 분석 완료")}</strong><p>{t("원본 분석 기준 · 자료 읽기 ")}{String(sourceDetails.coverage_summary || "범위 확인 필요")}{t(" → 문서/IR ")}{sourceAnalysis.ready_for_review ? t("완료") : "보완 필요"}{t(" → 실행 규칙 ")}{analysisReady ? t("완료") : "보완 필요"} → PAPER {analysisReady ? "승인 후 후보" : "시작 불가"}</p><p>{t("누락 조건 ")}{missingConditions.length}{t("개 · ")}{sourceAnalysis.provider_called ? "외부 AI 정밀 분석" : "로컬 규칙 기반 1차 추출"}{t(" · 편집한 최종값은 저장 직전에 서버에서 다시 검증")}</p></> : <p>{t("원본을 분석하면 출처 근거, 명시된 조건, 누락 조건, 위험, 엔진 설정값이 표시됩니다.")}</p>}</div>
      {sourceAnalysis && !analysisReady && authoringMode !== "guided_clarification" && <div className="strategy-authoring-next"><div><b>{t("무엇을 써야 할지 모르겠나요?")}</b><span>{t("현재 분석 결과는 그대로 두고, 빠진 조건만 한 항목씩 질문받을 수 있습니다.")}</span></div><button type="button" onClick={() => { setAuthoringMode("guided_clarification"); setMessage("현재 분석에서 빠진 조건을 질문 카드로 열었습니다. 자신의 전략 기준만 답해 주세요."); }}>{t("빠진 조건을 질문으로 완성")}</button></div>}
      {sourceSummary && <div className="inline-notice">{sourceSummary}</div>}
      {sourceAnalysis && authoringMode === "guided_clarification" && !analysisReady && <section className="strategy-clarification-panel" aria-live="polite">
        <header><div><span>{t("AI 전략 설계 인터뷰")}</span><h4>{t("모르는 값을 만들지 않고 사용자에게 확인합니다")}</h4><p>{t("질문에 자신의 기준을 적어 주세요. AI 예시는 설명일 뿐 자동 선택되지 않으며, 답변을 확정해도 저장·승인·PAPER·LIVE는 자동 실행되지 않습니다.")}</p></div><b>{clarificationQuestions.length}{t("개 확인")}</b></header>
        <ol>{clarificationQuestions.map((item, index) => { const key = clarificationKey(item, index); const resolution = String(item.resolution || "source_rewrite"); return <li key={key} className={resolution}>
          <div className="strategy-clarification-copy"><span>{index + 1}</span><div><strong>{String(item.title || "추가 확인 필요")}</strong><p>{String(item.question || item.action || "전략 조건을 구체적으로 설명해 주세요.")}</p><small>{t("왜 필요한가: ")}{String(item.why || item.explanation || "원문과 실행 규칙의 의미를 일치시키기 위해 필요합니다.")}</small>{item.example && <small>{t("입력 예시(자동 적용 안 됨): ")}{String(item.example)}</small>}</div></div>
          {resolution === "confirmed_selection" ? <button type="button" onClick={() => void insertConfirmedSupplement(item.code)}>{t("화면에서 고른 값을 확정하고 바로 재분석")}</button> : resolution === "user_answer" ? <label>{t("내 전략의 답변")}<textarea value={clarificationAnswers[key] || ""} onChange={(event) => setClarificationAnswers((current) => ({ ...current, [key]: event.target.value }))} placeholder={String(item.example || "조건·숫자·단위·LONG/SHORT를 포함해 적어 주세요.")} /></label> : <div className="strategy-clarification-rewrite"><b>{t("원본 수정 필요")}</b><span>{t("지원하지 않거나 의미가 풀리지 않은 조건입니다. AI가 비슷한 규칙으로 바꾸지 않습니다.")}</span></div>}
          {onAskAssistant && <button className="strategy-clarification-ask" type="button" onClick={() => onAskAssistant(`전략 스튜디오의 '${String(item.title || item.code)}' 질문을 초보자에게 설명해줘. 질문=${String(item.question || item.action || "")}, 예시=${String(item.example || "없음")}. 예시를 정답으로 정하거나 전략을 자동 수정하지 말고, 사용자가 자기 전략 기준을 말할 수 있도록 한 번에 하나의 확인 질문만 해줘.`)}>{t("이 질문을 AI와 상의")}</button>}
        </li>; })}</ol>
        <footer><span>{t("답변은 원본과 별도 해시로 기록됩니다. 파일·Pine·PDF는 덮어쓰지 않습니다.")}</span>{answerableClarifications.length > 0 ? <button className="primary-button" type="button" disabled={busy || !hasClarificationAnswer} onClick={() => void applyClarificationAnswers(clarificationQuestions)}>{t("답변 확정 후 다시 분석")}</button> : <b>{t("원본 수정 후 다시 분석하세요")}</b>}</footer>
      </section>}
      {sourceAnalysis && <div className="legacy-xai-sections">
        <StrategyBeginnerExplanation analysis={sourceAnalysis} name={name} service={service} />
        <section className="legacy-xai-card"><h4>{t("자료 분석 범위")}</h4><dl><div><dt>{t("자료 종류")}</dt><dd>{String(sourceDetails.kind ?? sourceKind)}</dd></div><div><dt>{t("출처")}</dt><dd>{String(sourceDetails.reference ?? sourceReference ?? "직접 입력")}</dd></div><div><dt>{t("읽은 범위")}</dt><dd>{String(sourceDetails.coverage_summary ?? "입력된 텍스트 범위")}</dd></div><div><dt>{t("분석 방식")}</dt><dd>{sourceAnalysis.provider_called ? "외부 AI API 정밀 분석" : "앱 내부 규칙 기반 추출 · API 비용 없음"}</dd></div></dl>{Object.keys(sourceEvidence).length > 0 && <details><summary>{t("영상·문서 근거 수집 정보")}</summary><pre>{JSON.stringify(sourceEvidence, null, 2)}</pre></details>}{analysisWarnings.length > 0 && <><h5>{t("자료 읽기 경고")}</h5><ul>{analysisWarnings.map((item: unknown, index: number) => <li key={index}>{readableDetail(item)}</li>)}</ul></>}</section>
        <section className={`legacy-xai-card ${missingConditions.length ? "warning" : "complete"}`}><h4>{t("누락 조건")}</h4>{missingConditions.length > 0 ? analysisBlockingDetails.length > 0 ? <ul className="legacy-xai-missing-list">{analysisBlockingDetails.map((item: Record<string, string>, index: number) => <li key={`${item.code}:${index}`}><b>{item.title}</b><span>{item.action}</span>{item.example && <small>{t("예: ")}{item.example}</small>}{canInsertConfirmedSupplement(item.code) && <button type="button" onClick={() => void insertConfirmedSupplement(item.code)}>{t("현재 선택값 확정·재분석")}</button>}</li>)}</ul> : <ul>{missingConditions.map((item: unknown, index: number) => <li key={index}>{readableDetail(item)}</li>)}</ul> : <p>{t("필수 구조 조건이 모두 확인되었습니다. 수익성이나 안전성이 보장된다는 의미는 아닙니다.")}</p>}</section>
        <section className={`legacy-xai-card ${analysisReady ? "complete" : "warning"}`}><h4>{t("실행 준비 상태")}</h4>{analysisReady ? <p>{t("승인 후 자동검증과 PAPER를 시작할 수 있습니다. 실제 적용과 수익을 보장하지는 않습니다.")}</p> : <><p>{t("전략 문서는 저장할 수 있지만 아직 승인·PAPER·적용할 수 없습니다.")}</p><ul>{(Array.isArray(analysisReadiness.reasons) ? analysisReadiness.reasons : []).map((item: unknown, index: number) => <li key={index}>{readinessReason(item)}</li>)}</ul></>}<small>{t("청산 정책: ")}{analysisReadiness.exit_policy_mode === "strategy_owned" ? "전략 자체 TP/SL" : "NoahAI 스마트 청산 상속"}</small></section>
        <section className="legacy-xai-card"><h4>{t("위험과 주의사항")}</h4>{analysisRisks.length > 0 ? <ul>{analysisRisks.map((item: unknown, index: number) => <li key={index}>{readableDetail(item)}</li>)}</ul> : <p>{t("추가로 추출된 위험 문장이 없습니다. PAPER 검증과 계정 가드레일은 계속 필요합니다.")}</p>}</section>
        {resultView !== "Level 1 이해·시험" && <>
          <section className="legacy-xai-card"><h4>{t("전략 규칙")}</h4><dl>{["entry", "exit", "stop_loss", "take_profit", "position_size", "market_conditions"].map((key) => <div key={key}><dt>{key}</dt><dd>{readableDetail(analysisRules[key])}</dd></div>)}</dl></section>
          <section className="legacy-xai-card"><h4>{t("엔진 적용값")}</h4><pre>{JSON.stringify(sourceAnalysis.engine_settings ?? analysisRules.engine_settings ?? {}, null, 2)}</pre></section>
          <section className="legacy-xai-card"><h4>{t("시장국면과 시험 시나리오")}</h4><p>{regimeSuggestionText}</p>{analysisScenarios.length > 0 ? <ul>{analysisScenarios.map((item: unknown, index: number) => <li key={index}>{readableDetail(item)}</li>)}</ul> : <p>{t("별도로 추출된 시험 시나리오가 없습니다.")}</p>}</section>
        </>}
        {(resultView === "Level 3 전체 근거" || resultView === "Level 4 전문가 운용") && <>
          <section className="legacy-xai-card legacy-xai-wide"><h4>{t("원문-규칙 추적")}</h4><pre>{JSON.stringify(sourceTrace, null, 2)}</pre></section>
          <section className="legacy-xai-card legacy-xai-wide"><h4>{t("Noah Strategy IR 전체")}</h4><pre>{JSON.stringify(sourceAnalysis.strategy_ir ?? {}, null, 2)}</pre></section>
        </>}
      </div>}
      {resultView === "Level 4 전문가 운용" && <section className="legacy-advanced-rule-editor"><header><div><b>{t("Level 4 전문가 운용 정책")}</b><small>{t("전략이 요청하는 범위를 정합니다. 최종값은 계좌 마스터 상한·시장·성과·거래소 규격 중 가장 안전한 값으로 다시 제한됩니다.")}</small></div></header><div className="form-grid legacy-strategy-identity"><label>{t("운용 정책")}<select value={riskPolicyPreset} onChange={(event) => { const key = event.target.value as keyof typeof RISK_POLICY_PRESETS; const preset = RISK_POLICY_PRESETS[key]; setRiskPolicyPreset(key); setRiskPerTrade(preset.riskPerTrade); setMaxMargin(preset.maxMargin); setLeverageCap(preset.leverageCap); setMaxConcurrentPositions(preset.maxPositions); setConflictFallback(preset.conflictFallback); }}><option value="conservative">{t("안정형")}</option><option value="standard">{t("표준형")}</option><option value="active">{t("적극형")}</option><option value="custom" disabled>{t("사용자 조정값")}</option></select></label><div><b>{t("전략 요청값")}</b><p>{t("거래당 ")}{riskPerTrade}% · {service === "stock" ? "종목 비중" : "증거금"} {maxMargin}{t("% · 레버리지 최대 ")}{service === "stock" ? "1" : leverageCap}{t("x · 동시 ")}{maxConcurrentPositions}{t("개")}</p></div><div><b>{t("현재 계좌 정책 상한")}</b><p>{t("거래당 ")}{accountRiskPolicy.riskPerTrade}% · {service === "stock" ? "종목 비중" : "증거금"} {accountRiskPolicy.maxMargin}{t("% · 기준 레버리지 ")}{service === "stock" ? "1" : accountRiskPolicy.defaultLeverage}{t("x · 동시 ")}{accountRiskPolicy.maxPositions}{t("개")}</p></div><div><b>{t("시장·성과 적용 전 허용값")}</b><p>{t("거래당 ")}{Math.min(Number(riskPerTrade) || 0, accountRiskPolicy.riskPerTrade)}% · {service === "stock" ? "종목 비중" : "증거금"} {Math.min(Number(maxMargin) || 0, accountRiskPolicy.maxMargin)}{t("% · 레버리지 최대 ")}{service === "stock" ? "1" : Math.min(Number(leverageCap) || 1, accountRiskPolicy.defaultLeverage)}{t("x · 동시 ")}{Math.min(Number(maxConcurrentPositions) || 1, accountRiskPolicy.maxPositions)}{t("개")}</p></div></div><p className="legacy-adapter-help">{t("현재 계좌 계산 방식: ")}{accountRiskPolicy.mode === "account_risk" ? t("NoahAI 자동 위험관리") : accountRiskPolicy.mode === "manual_notional" ? "수동 목표 거래 금액" : "기존 거래소별 호환"}{t(". 위 허용값도 시장·성과 제한과 거래소 규격이 더 낮으면 다시 축소되며, 주문 직전 XAI의 최종 Notional·예상손실·증거금·수량이 정본입니다. 계좌가 「수동 목표 거래 금액」이면 Notional은 고정되고, 「기존 거래소별 호환」이면 업데이트 전 수량 의미를 보존합니다. 전략 요청 위험이 최종 투자금에 반영되는 기본 모드는 「NoahAI 자동 위험관리」입니다. Level 5나 가드레일 해제 단계는 없습니다. 조절 불가: 사용자 승인·LIVE 명시 허용·일일 손실 중단·주문 최소금액/정밀도·TP/SL 보호·중복 주문 방지·포지션 대조·긴급 중지.")}</p></section>}
      {(resultView === "Level 3 전체 근거" || resultView === "Level 4 전문가 운용") && <section className="legacy-advanced-rule-editor"><header><div><b>{t("고급 실행 규칙 편집")}</b><small>{t("기관 이름과 상품 유형을 분리하며, 선택 범위 밖 기관에서는 실행 후보가 되지 않습니다.")}</small></div></header><div className="form-grid legacy-strategy-identity"><label>{t("전략 버전 이름")}<input value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label><div>{t("적용 실행 범위")}<fieldset className="venue-checkbox-picker"><legend>{t("거래소·증권사 복수 선택")}</legend><label><input type="checkbox" checked={executionTarget === allCompatibleTarget} onChange={(event) => { if (event.target.checked) changeExecutionTarget(allCompatibleTarget); }} />{t("호환되는 모든 기관")}</label>{compatibleVenueProfiles.map((profile) => {
            const prefix = service === "stock" ? "broker" : "exchange";
            const selected = executionTarget.startsWith(prefix + ":") ? executionTarget.split(":")[1].split(",") : [];
            return <label key={profile.id}><input type="checkbox" checked={selected.includes(profile.client_id)} onChange={(event) => {
              const next = event.target.checked ? [...selected, profile.client_id] : selected.filter((id) => id !== profile.client_id);
              if (!next.length) { setMessage("최소 한 기관을 선택하세요. 전체 범위는 별도로 선택해야 합니다."); return; }
              changeExecutionTarget(prefix + ":" + [...new Set(next)].sort().join(","));
            }} />{profile.display_name} · {profile.quote_currency}</label>;
          })}</fieldset></div></div><p className="legacy-adapter-help">{service === "stock" ? "전체 증권사 범위도 각 증권사의 주문 단위·거래시간·수수료·세금·성과를 따로 검증합니다. 특정 증권사를 선택하면 다른 증권사에서는 실행 후보가 되지 않습니다." : "전체 거래소 범위는 현물·선물 의미를 섞는다는 뜻이 아닙니다. 각 거래소의 SHORT·레버리지·계약수·최소주문·비용 능력을 통과한 경우에만 실행하고 성과는 기관·통화별로 분리합니다."}</p><label>{t("안전 선언형 규칙 JSON")}<textarea className="rule-editor" value={rulesText} spellCheck={false} onChange={(event) => { setRulesText(event.target.value); setUserDeclaredOverride(false); setDraftValidationIssues([]); }} /></label><label className={`legacy-rule-override-confirm ${userDeclaredOverride ? "checked" : ""}`}><input type="checkbox" checked={userDeclaredOverride} aria-describedby="legacy-rule-override-help" onChange={(event) => { setUserDeclaredOverride(event.target.checked); setDraftValidationIssues([]); }} /><span className="legacy-rule-override-copy"><strong>{t("직접 편집한 JSON을 사용자 선언 규칙으로 저장")}</strong><small>{t("위 JSON을 직접 수정한 경우에만 체크합니다. 원문 자동 변환 결과를 그대로 저장할 때는 체크할 필요가 없습니다.")}</small></span><b className="legacy-rule-override-state">{userDeclaredOverride ? "사용자 선언 확인됨" : "원문 자동 변환 유지"}</b></label><p id="legacy-rule-override-help" className="legacy-rule-override-help">{t("체크하지 않으면 원문과 실행값이 달라진 편집본은 저장 직전 차단됩니다. 체크해도 검증을 우회하지 않으며, 서버가 허용 필드·단위·위험·실행조건을 다시 검사하고 새 사용자 선언 해시를 기록합니다. 승인·과거 재생·PAPER·LIVE 적용은 여전히 각각 별도입니다.")}</p><p>{t("이 JSON은 AI 모델이나 별도 수익 엔진이 아니라, 허용된 지표·조건·위험 한도만 주문 계층에 전달하는 안전 규칙입니다. 임의 Python 실행, 파일·네트워크 접근, 출금 명령은 허용하지 않습니다.")}</p></section>}
      <div className="legacy-result-save-row"><small>{saveDisabledReason || "현재 편집값을 공통 주문 계약으로 다시 검증한 뒤 비활성 버전으로 저장합니다."}</small><button className="primary-button" title={saveDisabledReason || "최종 규칙 재검증 후 비활성 전략 버전으로 저장"} disabled={Boolean(saveDisabledReason)} onClick={createStrategy} type="button">{t("최종 재검증 후 전략 버전 저장")}</button></div>
      {draftValidationIssues.length > 0 && <section className="strategy-draft-validation-help" role="alert" aria-live="assertive"><header><div><strong>{t("저장 전에 확인할 항목 ")}{draftValidationIssues.length}{t("개")}</strong><span>{t("조건을 추측해서 실행하지 않도록 저장을 멈췄습니다. 원문을 보완한 뒤 다시 분석하는 방법이 가장 안전합니다.")}</span></div>{onAskAssistant && <button type="button" onClick={() => onAskAssistant(`전략 스튜디오 최종 재검증에서 다음 항목이 차단됐어. 초보자가 원문을 어떻게 고치면 되는지 순서와 예시로 설명해줘: ${draftValidationIssues.map((item) => `${item.title} (${item.code})`).join(", ")}`)}>{t("이 문제 AI에게 묻기")}</button>}</header><ol>{draftValidationIssues.map((item, index) => <li key={`${item.code}:${index}`}><div><b>{index + 1}. {item.title || "추가 확인 필요"}</b><p>{item.explanation || "원문과 실행 규칙을 다시 확인하세요."}</p><strong>{t("고치는 방법")}</strong><p>{item.action || "원문 조건을 구체적으로 작성한 뒤 다시 분석하세요."}</p>{item.example && <small>{t("입력 예시: ")}{item.example}</small>}<details><summary>{t("기술 코드 보기")}</summary><code>{item.code}</code></details></div></li>)}</ol><footer>{t("권장 순서: 원문 수정 → 「AI 분석 및 전략 초안 만들기」 → XAI 누락 조건 확인 → 「최종 재검증 후 전략 버전 저장」")}</footer></section>}
    </article>
    <article className="panel studio-panel">
      <div className="panel-heading"><div><span className="eyebrow">NOAH STRATEGY IR · PRIVATE</span><h2>{t("3. 내 프라이빗 전략 버전")}</h2></div><div className="toolbar"><span className="active-pool-count">{t("실행 풀 ")}{catalog?.strategies.filter((strategy) => strategy.versions.some((version) => version.active)).length ?? 0}/10</span>{featureViewLevel >= 2 && <label className="package-import">{t("전략 가져오기")}<input type="file" accept=".noahstrategy,application/json" onChange={(event) => { void importPackage(event.target.files?.[0] ?? null); event.currentTarget.value = ""; }} /></label>}<a className="secondary-button strategy-submit-link" href={STRATEGY_HUB_LIBRARY_URL} target="_blank" rel="noreferrer">{t("내 전략 라이선스")}</a><a className="secondary-button strategy-submit-link" href={STRATEGY_HUB_SUBMIT_URL} target="_blank" rel="noreferrer">{t("내 전략 제출")}</a><button className="secondary-button" onClick={refresh} type="button">{t("새로고침")}</button></div></div>
      <details className="strategy-import-help"><summary>{t("허브 제출·다운로드·외부 검증 기록 안내")}</summary><p>{t("「전략 둘러보기」는 공개 전략과 검증 여권을 보는 화면입니다. 「내 전략 라이선스」는 daltrading 회원 전용이며 브라우저에 로그인되어 있지 않으면 로그인한 뒤 자동으로 라이선스 화면으로 돌아옵니다. NoahAI 앱 로그인과 브라우저 로그인은 서로 다른 세션입니다. 내 전략 제출은 자동 업로드가 아닙니다. 공개할 버전의 「패키지 내보내기」로 파일을 받은 뒤 「내 전략 제출」에서 로그인하고 권리·공개 설명을 확인해 직접 제출합니다. daltrading 제출 화면의 거래소·증권사와 시장국면은 직접 입력이 아니라 체크박스로 선택합니다. 검증 실패 시 작성 내용과 선택값은 보존되고 브라우저 보안상 전략 파일만 다시 선택합니다. 허브 전략의 첫 무료 다운로드는 daltrading 계정에 취득 기록과 해당 버전의 영구·비독점 실행 라이선스를 발급하며 「내 전략 라이선스」에서 다시 받을 수 있습니다. 가져올 때만 운영체제 파일 선택창에서 .noahstrategy 파일을 찾습니다. 검증이 끝나면 현재 NoahAI 계정의 기본 전략 저장소(Documents/NoahAI/<계정>/custom_strategies)에 비활성 검토 버전으로 복사되므로 다음부터 파일을 다시 찾을 필요가 없습니다. 허브에서 받은 파일도 자동 적용되지 않으며 사용자 승인·과거 재생·PAPER를 다시 거칩니다.")}</p></details>
      {message && <div className="inline-notice">{message}</div>}
      <div className="strategy-list">
        {!busy && !catalog?.strategies.length && <div className="empty-state"><strong>{t("저장된 프라이빗 전략이 없습니다.")}</strong><span>{t("위 입력 영역에서 원본 분석 → XAI 검토 → 버전 저장 순서로 만들 수 있습니다.")}</span><button className="primary-button" type="button" onClick={openGuidedTour}>{t("처음 사용 · 5분 따라 만들기")}</button></div>}
        {catalog?.strategies.map((strategy) => <article className="strategy-card" key={`${strategy.scope}:${strategy.strategy_key}`}>
          <header><div><span>{strategy.scope.toUpperCase()}</span><strong>{strategy.versions.at(-1)?.name ?? strategy.strategy_key}</strong><small>{strategy.strategy_key}</small></div><button className="danger-button" disabled={busy || strategy.versions.some((version) => version.active || version.paper_observing)} onClick={() => remove(strategy.scope, strategy.strategy_key)} type="button">{t("전략 전체 삭제")}</button></header>
          <div className="version-list">{[...strategy.versions].reverse().map((version) => { const label = actionLabel(version); const replayApplicable = historicalReplayApplicable(version); const validationAction = !version.active && replayApplicable && ["approved", "execution_rejected"].includes(version.status); const directPaperAction = !version.active && !replayApplicable && ["approved", "execution_rejected"].includes(version.status); const action = validationAction ? "validate" : directPaperAction ? "start_paper" : version.active ? "deactivate" : (version.paper_observing || version.status === "paper_observing") ? "stop_paper" : version.status === "paper_paused" ? "start_paper" : version.status === "analyzed" ? "approve" : version.status === "execution_validated" && version.execution_validation?.mode === "historical_replay" ? "start_paper" : "activate"; const readiness = version.execution_readiness ?? version.paper_execution_readiness; const paperReady = readiness?.ready !== false; const canStartPaperDirectly = replayApplicable && paperReady && !version.active && !version.paper_observing && ["approved", "execution_rejected", "paper_rejected"].includes(version.status); const paperMetrics = version.paper_validation?.metrics ?? {}; const paperCompletion = String(version.paper_validation?.completion_status ?? (version.paper_validation?.passed ? "passed" : "in_progress")); const paperProgress = version.paper_progress ?? { trades: Number(version.paper_validation?.trades ?? 0), observation_days: Number(paperMetrics.observation_days ?? 0), required_trades: 3, required_days: 7 }; const attemptHistory = version.paper_validation_attempt_history ?? []; const legacyValidationHistory = version.paper_validation_history ?? []; const preservedHistory = attemptHistory.length ? attemptHistory : legacyValidationHistory.map((paper_validation) => ({ paper_validation, reason: "v3.9.1.22 이전 보존 근거" })); return <div className="version-row" key={version.version_id}>
            <div><b>v{version.version}</b><span className={`state-pill ${version.active ? "active" : ""}`}>{strategyStatusLabel(version)}</span><small className="strategy-version-created">{strategyVersionTime((version as any).created_at)}</small></div>
            <div className="version-summary"><strong>{version.xai?.summary ?? "XAI 설명 준비 중"}</strong><span>{version.source_kind ?? "manual"} · {version.source_reference ?? "원본 직접 입력"} · {version.missing_conditions.length ? `확인 필요 ${version.missing_conditions.length}개` : "문서/IR 확인 완료"}{t(" · 실행 규칙 ")}{paperReady ? t("완료") : "보완 필요"}</span><small>{!paperReady ? `승인·PAPER·적용 차단 · ${(readiness?.reasons ?? []).map(readinessReason).join(" ")} 이 보관 버전은 기본 NoahAI 거래를 차단하지 않습니다.` : version.active ? `최종 적용됨 · 앱 PAPER에서는 가상 실행, LIVE에서는 승인 범위 실행${version.paper_validation ? ` · PAPER ${Number(version.paper_validation.trades ?? 0)}건` : ""}` : version.paper_observing || version.status === "paper_observing" ? `PAPER 검증 중 · ${Number(paperProgress.trades ?? 0)}/${Number(paperProgress.required_trades ?? 3)}건 · 활성 검증 ${Number(paperProgress.observation_days ?? 0).toFixed(1)}/${Number(paperProgress.required_days ?? 7)}일` : version.status === "paper_paused" ? `PAPER 일시정지 · 근거 보존 ${Number(paperProgress.trades ?? 0)}건 · 활성 검증 ${Number(paperProgress.observation_days ?? 0).toFixed(1)}일 · 재개 시 이어서 계산` : version.paper_validation ? `PAPER ${paperCompletion === "passed" ? "통과" : paperCompletion === "failed" ? "미통과" : "진행 근거"} · ${Number(version.paper_validation.trades ?? 0)}건` : version.execution_validation?.mode === "historical_replay" ? `과거재생 ${version.execution_validation.passed ? "최소 통과" : "미통과"} · PAPER 시작 필요` : !replayApplicable ? "과거재생 비대상 · NoahAI 기본 진입과 함께 PAPER에서 위험·청산 규칙 검증" : "PAPER 결과 없음"}</small><p className="strategy-evidence-warning">{replayApplicable ? "검증 대상: 구조화된 사용자 진입·청산 규칙" : "검증 대상: NoahAI 기본 진입 + 사용자 위험·청산값. 원문 전체 진입 전략의 검증 결과가 아닙니다."}</p><StrategyValidationEvidence version={version} /><StrategyVersionContract version={version} />{preservedHistory.length > 0 && <details><summary>{t("이전 PAPER 검증 시도 ")}{preservedHistory.length}{t("개 · 근거 보존")}</summary><pre className="json-summary">{JSON.stringify(preservedHistory, null, 2)}</pre></details>}{version.version > 1 && Boolean(version.version_diff?.changes?.length) && <details><summary>{t("이전 버전과 변경점 ")}{version.version_diff?.changes?.length}{t("개")}</summary><pre className="json-summary">{JSON.stringify(version.version_diff, null, 2)}</pre></details>}</div>
            <div className="row-actions">{label && <button className="primary-button" title={!paperReady && action === "approve" ? "실행 규칙을 보완해야 승인할 수 있습니다." : undefined} disabled={busy || (!paperReady && ["approve", "validate", "start_paper", "activate"].includes(action))} onClick={() => runAction(version, strategy.scope)} type="button">{label}</button>}{canStartPaperDirectly && <button className="secondary-button" disabled={busy} onClick={() => runAction(version, strategy.scope, "start_paper")} type="button">{t("PAPER 전진검증 시작")}</button>}{version.status === "paper_paused" && <button className="secondary-button" disabled={busy} onClick={() => runAction(version, strategy.scope, "restart_paper")} type="button">{t("새 검증 시작")}</button>}{featureViewLevel >= 2 && <button className="secondary-button" disabled={busy} onClick={() => exportExecutionEvidence(strategy.scope, version)} title={t("이 버전의 PAPER 진입 국면·방향·가격·보유시간·수량 제한·비용·손익·TP/SL·Smart Exit 근거를 로컬 JSON으로 저장합니다.")} type="button">{t("검증 거래 내보내기")}</button>}{featureViewLevel >= 2 && <button className="secondary-button" disabled={busy} onClick={() => exportPackage(strategy.scope, version)} type="button">{t("패키지 내보내기")}</button>}<a className="secondary-button strategy-submit-link" href={STRATEGY_HUB_SUBMIT_URL} target="_blank" rel="noreferrer" title={t("패키지를 내보낸 뒤 daltrading 1단계에서 서버 분석, 2단계에서 추출 범위와 배포 권리를 확인합니다.")}>{t("허브에 제출")}</a>{!version.active && (version.paper_validation?.passed || (["live_observation", "limited_live"].includes(String(version.execution_validation?.mode ?? "")) && version.execution_validation?.passed)) && <button className="secondary-button" disabled={busy} onClick={() => rollback(strategy.scope, version)} type="button">{t("이 버전으로 롤백")}</button>}<button className="danger-button" disabled={busy || version.active || version.paper_observing} onClick={() => remove(strategy.scope, strategy.strategy_key, version.version_id)} type="button">{t("버전 삭제")}</button></div>
          </div>; })}</div>
        </article>)}
      </div>
    </article>
    </div>
  </section>;
}
