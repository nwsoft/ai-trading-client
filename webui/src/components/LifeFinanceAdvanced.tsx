import { t } from '../i18n';
import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";
import { InsuranceBudgetSummary } from "./InsuranceWorkspace";

import { GuidedProductComparison } from "./GuidedProductComparison";

function money(value: unknown) {
  return value == null || !Number.isFinite(Number(value)) ? "미확인" : Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

type TaxDraft = Record<string, string> & { calculation: string };

const TAX_INPUTS: Record<string, Array<[string, string, string?]>> = {
  year_end: [
    ["annual_salary", "연간 급여"], ["credit_card", "신용카드 사용액"], ["debit_cash", "체크카드·현금영수증"],
    ["medical_expense", "의료비"], ["education_expense", "교육비"], ["donation", "기부금"],
    ["pension_savings", "연금저축 납입액"], ["irp_contribution", "IRP 납입액"], ["personal_deduction_count", "인적공제 인원", "1"],
  ],
  financial_income: [["annual_salary", "연간 급여"], ["interest_income", "이자 소득"], ["dividend_income", "배당 소득"]],
  investment: [
    ["domestic_stock_profit", "국내 주식 손익"], ["overseas_stock_profit", "해외 주식 손익"],
    ["etf_profit", "ETF 손익"], ["other_profit", "기타 투자 손익"],
  ],
  saving_accounts: [
    ["annual_salary", "연간 급여"], ["annual_investment", "연간 투자액"], ["investment_years", "투자 기간(년)", "1"],
    ["expected_return_rate", "예상 연 수익률(0~1)", "0.001"],
  ],
  optimization: [
    ["annual_salary", "연간 급여"], ["pension_savings", "연금저축 납입액"], ["irp_contribution", "IRP 납입액"],
    ["credit_card", "신용카드 사용액"], ["debit_cash", "체크카드·현금영수증"], ["medical_expense", "의료비"],
    ["education_expense", "교육비"], ["donation", "기부금"], ["interest_income", "이자 소득"], ["dividend_income", "배당 소득"],
  ],
};


const TAX_LABELS: Record<string, string> = {
  annual_salary: "연간 급여",
  earned_income_deduction: "근로소득공제",
  personal_deduction: "인적공제",
  card_income_deduction: "카드 소득공제",
  taxable_income: "과세표준",
  base_tax: "산출세액",
  medical_tax_credit: "의료비 세액공제",
  education_tax_credit: "교육비 세액공제",
  donation_tax_credit: "기부금 세액공제",
  pension_tax_credit: "연금 세액공제",
  total_tax_credit: "총 세액공제",
  final_tax: "예상 결정세액",
  total_deduction_effect: "총 공제 효과",
  total_financial_income: "금융소득 합계",
  subject_to_comprehensive_tax: "종합과세 대상",
  excess_amount: "기준 초과액",
  withholding_tax: "원천징수 추정액",
  domestic_tax: "국내 주식 세액",
  overseas_tax: "해외 주식 세액",
  etf_tax: "ETF 세액",
  total_tax: "예상 세액 합계",
  effective_rate: "실효세율",
  salary_tax_credit_rate: "급여 기준 세액공제율",
  best_scenario: "가장 유리한 절세 계좌",
  current_tax_credit_total: "현재 세액공제 합계",
  unused_pension_savings_room: "연금저축 추가 활용 가능액",
  unused_irp_room: "IRP 추가 활용 가능액",
  message: "판정 안내",
  disclaimer: "유의사항",
};

const PRODUCT_FIELD_LABELS: Record<string, string> = {
  annual_rate: "연이율",
  loan_type: "대출 종류",
  total_cost: "총비용",
  monthly_payment: "월 납입액",
  monthly_premium: "월 보험료",
  coverage_score: "보장점수",
  deductible: "자기부담금",
  expected_interest: "예상 이자",
  tax_free: "비과세",
};

function displayValue(key: string, value: unknown) {
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "number") {
    if (key.includes("rate")) return `${(value <= 1 ? value * 100 : value).toLocaleString(undefined, { maximumFractionDigits: 2 })}%`;
    if (key.includes("score")) return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}/100`;
    return `${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}원`;
  }
  return String(value ?? "-");
}

function suggestionText(value: unknown) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return String(value ?? "-");
  const row = value as Record<string, unknown>;
  return String(row.message ?? row.suggestion ?? row.title ?? Object.values(row).filter((item) => ["string", "number"].includes(typeof item)).join(" · ") ?? "점검 제안");
}

export function LifeFinanceAdvanced({ client, featureId }: { client: GatewayClient; featureId: string }) {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [taxResult, setTaxResult] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tax, setTax] = useState<TaxDraft>({
    calculation: "year_end", annual_salary: "50000000", credit_card: "0", debit_cash: "0", medical_expense: "0",
    education_expense: "0", donation: "0", pension_savings: "0", irp_contribution: "0", personal_deduction_count: "1",
    interest_income: "0", dividend_income: "0", domestic_stock_profit: "0", overseas_stock_profit: "0", etf_profit: "0",
    other_profit: "0", annual_investment: "6000000", investment_years: "5", expected_return_rate: "0.05", isa_type: "general",
  });

  const load = () => {
    if (featureId.endsWith("products")) return Promise.resolve();
    const request = client.lifeFinanceAnalysis();
    return request.then((next) => { setData(next); setError(""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "생활금융 기능 조회 실패"));
  };

  useEffect(() => { void load(); }, [client, featureId]);

  async function calculateTax() {
    setBusy(true); setError("");
    try {
      const next = await client.calculateLifeTax(Object.fromEntries(Object.entries(tax).map(([key, value]) => [key, key === "calculation" || key === "isa_type" ? value : Number(value)])));
      setTaxResult(next);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "세금 계산 실패"); }
    finally { setBusy(false); }
  }

  if (featureId.endsWith("products")) return <GuidedProductComparison client={client} />;

  if (featureId.endsWith("security")) {
    const alerts = (data?.alerts ?? []) as Array<Record<string, any>>;
    return <section className="data-workspace"><article className="panel life-security-panel"><div className="panel-heading"><div><span className="eyebrow">SAFETY</span><h2>{t("금융 보안 경고 센터")}</h2><p>{t("등록된 기록의 경고를 표시합니다. 은행 전체 거래망의 실시간 사기 탐지나 모든 보이스피싱 차단을 뜻하지 않습니다.")}</p></div></div><p className="workspace-copy">{t("생활금융 거래·목표 정본에서 이상 패턴과 주의 항목을 확인합니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="alert-list">{alerts.map((alert, index) => <section className={`alert-card ${String(alert.level ?? "info")}`} key={`${alert.title}-${index}`}><strong>{String(alert.title)}</strong><p>{String(alert.message)}</p><small>{String(alert.action_hint)}</small></section>)}{!alerts.length && <div className="empty-state">{t("현재 기록에서 생성된 생활금융 경고가 없습니다.")}</div>}</div></article></section>;
  }

  if (featureId.endsWith("tax")) {
    return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">TAX REFERENCE</span><h2>{t("세금 계산 & 절세 시뮬레이터")}</h2></div></div><p className="workspace-copy">{t("간이 계산이며 귀속연도별 전체 세법·예외 사례 검증을 마친 신고 계산기가 아닙니다. 기납부세액·모든 공제를 반영한 환급액이 아닙니다. 금투세는 폐지되어 계산하지 않습니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="form-grid advanced-form"><label>{t("계산 유형")}<select value={tax.calculation} onChange={(event) => { setTax({ ...tax, calculation: event.target.value }); setTaxResult(null); }}><option value="year_end">{t("연말정산")}</option><option value="financial_income">{t("금융소득 종합과세")}</option><option value="investment">금투세 폐지 · 투자소득 과세 안내</option><option value="saving_accounts">{t("절세 계좌 비교")}</option><option value="optimization">{t("절세 최적화")}</option></select></label>{(tax.calculation === "investment" ? [] : TAX_INPUTS[tax.calculation] ?? []).map(([key, label, step]) => <label key={key}>{label}<input type="number" min={key.includes("profit") ? undefined : "0"} step={step ?? "1"} value={tax[key] ?? "0"} onChange={(event) => setTax({ ...tax, [key]: event.target.value })} /></label>)}{tax.calculation === "saving_accounts" && <label>{t("ISA 유형")}<select value={tax.isa_type} onChange={(event) => setTax({ ...tax, isa_type: event.target.value })}><option value="general">{t("일반형")}</option><option value="preferential">{t("서민형·농어민형")}</option></select></label>}</div><div className="command-row"><button className="primary-button" type="button" disabled={busy} onClick={calculateTax}>{busy ? "처리 중…" : tax.calculation === "investment" ? "제도 안내 확인" : "세금 계산하기"}</button></div>{taxResult && <TaxResult response={taxResult} />}</article></section>;
  }

  return <><InsuranceBudgetSummary client={client} /><FinanceAnalysis data={data} error={error} chartOnly={featureId.endsWith("chart")} /></>;
}

function TaxResult({ response }: { response: Record<string, any> }) {
  const result = (response.result ?? {}) as Record<string, any>;
  if (result.status === "abolished_regime") return <section className="panel finance-tax-notice" aria-label="투자소득 과세 안내"><h3>세액 미계산 · 폐지 제도</h3><p>{String(result.message)}</p><p>{String(result.disclaimer)}</p><a href="https://www.law.go.kr/lsInfoP.do?chrClsCd=010102&lsiSeq=282431&viewCls=lsRvsDocInfoR" target="_blank" rel="noreferrer">공식 개정 근거 확인</a><small> 확인일 2026-10-02</small></section>;
  const scalarEntries = Object.entries(result).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value));
  const scenarios = result.scenarios && typeof result.scenarios === "object" ? Object.entries(result.scenarios as Record<string, Record<string, unknown>>) : [];
  const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];
  return <section className="legacy-tax-result" aria-label={t("세금 계산 결과")}><div className="panel-heading"><div><span className="eyebrow">CALCULATION RESULT</span><h3>{t("세금 계산 결과")}</h3></div><span className="count-badge">{t("참고용")}</span></div><div className="metric-grid tax-metric-grid">{scalarEntries.filter(([key]) => !["message", "disclaimer"].includes(key)).map(([key, value]) => <div key={key}><span>{TAX_LABELS[key] ?? key.replaceAll("_", " ")}</span><strong>{displayValue(key, value)}</strong></div>)}</div>{scenarios.length > 0 && <div className="card-grid">{scenarios.map(([name, values]) => <article className="insight-card" key={name}><header><strong>{name}</strong></header><dl>{Object.entries(values).map(([key, value]) => <div key={key}><dt>{TAX_LABELS[key] ?? PRODUCT_FIELD_LABELS[key] ?? key.replaceAll("_", " ")}</dt><dd>{displayValue(key, value)}</dd></div>)}</dl></article>)}</div>}{suggestions.length > 0 && <div className="recommendation-list"><h3>{t("절세 점검 제안")}</h3>{suggestions.map((item: unknown, index: number) => <p key={index}>• {suggestionText(item)}</p>)}</div>}{result.message && <p className="inline-notice">{String(result.message)}</p>}<p className="workspace-copy">{String(result.disclaimer ?? "계산 결과는 참고용이며 실제 신고 결과와 다를 수 있습니다.")}</p></section>;
}

function FinanceAnalysis({ data, error, chartOnly }: { data: Record<string, any> | null; error: string; chartOnly: boolean }) {
  const monthlySavings = Object.entries(data?.monthly_savings ?? {}) as Array<[string, number]>;
  const spendingMap = useMemo(() => Object.fromEntries(Object.entries(data?.spending_trend ?? {})), [data]);
  const basis = (data?.projection_basis ?? {}) as Record<string, any>;
  if (chartOnly) return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">12 MONTHS</span><h2>{t("고급 차트")}</h2></div></div><p className="workspace-copy">{t("등록된 월별 수입−지출과 지출을 표시합니다. 기록 없는 달은 제외하며 월중 기록을 연간 예측으로 확대하지 않습니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="trend-grid">{monthlySavings.map(([month, saving]) => <div key={month}><span>{month}</span><strong>{money(saving)}{t("원")}</strong><small>{t("지출 ")}{money(spendingMap[month])}{t("원")}</small></div>)}</div>{!monthlySavings.length && <div className="empty-state">{t("차트를 만들 생활금융 기록이 없습니다.")}</div>}</article></section>;
  return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">PERSONAL FINANCE ANALYTICS</span><h2>{t("재무 분석")}</h2></div></div><p className="workspace-copy">{t("등록된 생활금융 기록만 계산합니다. 기록 없음은 실제 0원이 아닙니다. 월간 계획 비교는 대시보드에서 가정을 입력하세요.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="metric-grid"><div><span>{t("이번 달 수입")}</span><strong>{money(basis.monthly_income)}{t("원")}</strong></div><div><span>{t("이번 달 지출")}</span><strong>{money(basis.monthly_expenses)}{t("원")}</strong></div><div><span>{t("계획 비교")}</span><strong>가정 입력 필요</strong></div><div><span>{t("경고")}</span><strong>{Number(data?.alerts?.length ?? 0)}{t("건")}</strong></div></div></article><article className="panel"><div className="panel-heading"><div><span className="eyebrow">CATEGORY</span><h2>{t("지출 카테고리 분석")}</h2></div></div><div className="card-grid">{Object.entries(data?.category_stats ?? {}).map(([category, row]) => <section className="insight-card" key={category}><header><strong>{category}</strong><span>{Number((row as any).count ?? 0)}{t("건")}</span></header><dl><dt>{t("합계")}</dt><dd>{money((row as any).total)}{t("원")}</dd><dt>{t("평균")}</dt><dd>{money((row as any).avg)}{t("원")}</dd></dl></section>)}</div></article></section>;
}
