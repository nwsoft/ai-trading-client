import { t } from '../i18n';
import { useEffect, useMemo, useState } from "react";

import type { GatewayClient } from "../api";

function money(value: unknown) {
  return Number(value ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 });
}

type ProductKind = "loan" | "insurance" | "savings";
type ProductResults = Partial<Record<ProductKind, Record<string, any>>>;
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

const PRODUCT_LABELS: Record<ProductKind, string> = {
  loan: "대출 비교",
  insurance: "보험 비교",
  savings: "예적금 비교",
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
  const [results, setResults] = useState<ProductResults>({});
  const [taxResult, setTaxResult] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState({ credit: "보통 (650~750)", risk: "보수형" });
  const [loan, setLoan] = useState({ amount_wan: "10000", term_months: "24" });
  const [insurance, setInsurance] = useState({ monthly_budget: "70000", category: "전체" });
  const [savings, setSavings] = useState({ principal_wan: "500", term_months: "12" });
  const [tax, setTax] = useState<TaxDraft>({
    calculation: "year_end", annual_salary: "50000000", credit_card: "0", debit_cash: "0", medical_expense: "0",
    education_expense: "0", donation: "0", pension_savings: "0", irp_contribution: "0", personal_deduction_count: "1",
    interest_income: "0", dividend_income: "0", domestic_stock_profit: "0", overseas_stock_profit: "0", etf_profit: "0",
    other_profit: "0", annual_investment: "6000000", investment_years: "5", expected_return_rate: "0.05", isa_type: "general",
  });

  const load = () => {
    const request = featureId.endsWith("products") ? client.financeProducts() : client.lifeFinanceAnalysis();
    return request.then((next) => { setData(next); setError(""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "생활금융 기능 조회 실패"));
  };

  useEffect(() => { void load(); }, [client, featureId]);

  function productPayload(kind: ProductKind): Record<string, unknown> {
    if (kind === "loan") return { product_type: kind, amount: Number(loan.amount_wan) * 10_000, term_months: Number(loan.term_months), category: null, credit_score: profile.credit };
    if (kind === "insurance") return { product_type: kind, amount: Number(insurance.monthly_budget), term_months: 12, category: insurance.category === "전체" ? null : insurance.category, credit_score: profile.credit };
    return { product_type: kind, amount: Number(savings.principal_wan) * 10_000, term_months: Number(savings.term_months), category: null, credit_score: profile.credit };
  }

  async function runComparison(kind?: ProductKind) {
    setBusy(true); setError("");
    try {
      if (kind) {
        const next = await client.compareFinanceProduct(productPayload(kind));
        setResults((current) => ({ ...current, [kind]: next }));
      } else {
        const [loanResult, insuranceResult, savingsResult] = await Promise.all([
          client.compareFinanceProduct(productPayload("loan")),
          client.compareFinanceProduct(productPayload("insurance")),
          client.compareFinanceProduct(productPayload("savings")),
        ]);
        setResults({ loan: loanResult, insurance: insuranceResult, savings: savingsResult });
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "상품 비교 실패"); }
    finally { setBusy(false); }
  }

  async function calculateTax() {
    setBusy(true); setError("");
    try {
      const next = await client.calculateLifeTax(Object.fromEntries(Object.entries(tax).map(([key, value]) => [key, key === "calculation" || key === "isa_type" ? value : Number(value)])));
      setTaxResult(next);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "세금 계산 실패"); }
    finally { setBusy(false); }
  }

  if (featureId.endsWith("products")) {
    return <section className="data-workspace">
      <article className="panel legacy-product-workspace">
        <div className="panel-heading"><div><span className="eyebrow">PRODUCT COMPARISON</span><h2>{t("금융상품 비교")}</h2></div></div>
        <p className="workspace-copy">{t("기존 클라이언트와 같은 대출·보험·예적금 조건을 각각 비교합니다. 정보 제공 전용이며 가입 신청이나 수익 보장을 하지 않습니다.")}</p>
        {error && <div className="inline-notice error-text">{error}</div>}
        <section className="legacy-product-profile">
          <h3>{t("개인화 프로필")}</h3>
          <div className="form-grid legacy-product-profile-fields">
            <label>{t("신용도")}<select value={profile.credit} onChange={(event) => setProfile({ ...profile, credit: event.target.value })}><option value={"좋음 (750~900)"}>{t("좋음 (750~900)")}</option><option value={"보통 (650~750)"}>{t("보통 (650~750)")}</option><option value={"낮음 (~650)"}>{t("낮음 (~650)")}</option></select></label>
            <label>{t("위험도")}<select value={profile.risk} onChange={(event) => setProfile({ ...profile, risk: event.target.value })}><option value={"회피형"}>{t("회피형")}</option><option value={"보수형"}>{t("보수형")}</option><option value={"공격형"}>{t("공격형")}</option></select></label>
          </div>
        </section>
        <section className="legacy-product-conditions">
          <h3>{t("금융상품 비교 조건 설정")}</h3>
          <div className="legacy-product-condition-grid">
            <div className="form-grid advanced-form">
              <label>{t("대출 금액(만원)")}<input type="number" min="1" value={loan.amount_wan} onChange={(event) => setLoan({ ...loan, amount_wan: event.target.value })} /></label>
              <label>{t("대출 기간(개월)")}<input type="number" min="1" max="600" value={loan.term_months} onChange={(event) => setLoan({ ...loan, term_months: event.target.value })} /></label>
              <label>{t("보험 월 예산(원)")}<input type="number" min="1" value={insurance.monthly_budget} onChange={(event) => setInsurance({ ...insurance, monthly_budget: event.target.value })} /></label>
              <label>{t("보험 종류")}<select value={insurance.category} onChange={(event) => setInsurance({ ...insurance, category: event.target.value })}><option value={"전체"}>{t("전체")}</option><option value={"종합"}>{t("종합")}</option><option value={"건강"}>{t("건강")}</option><option value={"가족"}>{t("가족")}</option></select></label>
              <label>{t("원금(만원)")}<input type="number" min="1" value={savings.principal_wan} onChange={(event) => setSavings({ ...savings, principal_wan: event.target.value })} /></label>
              <label>{t("기간(개월)")}<input type="number" min="1" max="600" value={savings.term_months} onChange={(event) => setSavings({ ...savings, term_months: event.target.value })} /></label>
            </div>
            <div className="command-row legacy-product-actions"><button type="button" disabled={busy} onClick={() => runComparison("loan")}>{t("대출 비교")}</button><button type="button" disabled={busy} onClick={() => runComparison("insurance")}>{t("보험 비교")}</button><button type="button" disabled={busy} onClick={() => runComparison("savings")}>{t("예적금 비교")}</button><button type="button" disabled={busy} onClick={() => runComparison()}>{t("전체 비교")}</button></div>
          </div>
        </section>
        <small className="workspace-copy">{t("신용도는 원본과 동일하게 대출·예적금 비교의 우대/가산 금리 안내에 반영됩니다. 위험도는 AI 상담 문맥에만 사용하며 상품 가입이나 신청은 실행하지 않습니다.")}</small>
        <div className="legacy-product-catalog"><span>{Object.entries(data?.counts ?? {}).map(([name, count]) => `${PRODUCT_LABELS[name as ProductKind] ?? name} ${Number(count)}개`).join(" · ") || "상품 정보 확인 중..."}</span><button className="secondary-button" type="button" onClick={load}>{t("상품 정보 다시 읽기")}</button></div>
      </article>
      {(Object.entries(results) as Array<[ProductKind, Record<string, any>]>).map(([kind, response]) => <ProductResult key={kind} kind={kind} response={response} />)}
    </section>;
  }

  if (featureId.endsWith("security")) {
    const alerts = (data?.alerts ?? []) as Array<Record<string, any>>;
    return <section className="data-workspace"><article className="panel life-security-panel"><div className="panel-heading"><div><span className="eyebrow">SAFETY</span><h2>{t("금융 보안 경고 센터")}</h2><p>{t("보이스피싱·스미싱·이상거래·약탈적 대출 패턴을 자동 감지합니다. 모든 결과는 참고용이며 오탐이 있을 수 있습니다.")}</p></div></div><p className="workspace-copy">{t("생활금융 거래·목표 정본에서 이상 패턴과 주의 항목을 확인합니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="alert-list">{alerts.map((alert, index) => <section className={`alert-card ${String(alert.level ?? "info")}`} key={`${alert.title}-${index}`}><strong>{String(alert.title)}</strong><p>{String(alert.message)}</p><small>{String(alert.action_hint)}</small></section>)}{!alerts.length && <div className="empty-state">{t("현재 기록에서 생성된 생활금융 경고가 없습니다.")}</div>}</div></article></section>;
  }

  if (featureId.endsWith("tax")) {
    return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">TAX REFERENCE</span><h2>{t("세금 계산 & 절세 시뮬레이터")}</h2></div></div><p className="workspace-copy">{t("결과는 참고용이며 공식 신고·세무 자문이 아닙니다. 신고 전에는 반드시 최신 법령과 국세청 자료를 확인하세요.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="form-grid advanced-form"><label>{t("계산 유형")}<select value={tax.calculation} onChange={(event) => { setTax({ ...tax, calculation: event.target.value }); setTaxResult(null); }}><option value="year_end">{t("연말정산")}</option><option value="financial_income">{t("금융소득 종합과세")}</option><option value="investment">{t("금융투자소득")}</option><option value="saving_accounts">{t("절세 계좌 비교")}</option><option value="optimization">{t("절세 최적화")}</option></select></label>{(TAX_INPUTS[tax.calculation] ?? []).map(([key, label, step]) => <label key={key}>{label}<input type="number" min={key.includes("profit") ? undefined : "0"} step={step ?? "1"} value={tax[key] ?? "0"} onChange={(event) => setTax({ ...tax, [key]: event.target.value })} /></label>)}{tax.calculation === "saving_accounts" && <label>{t("ISA 유형")}<select value={tax.isa_type} onChange={(event) => setTax({ ...tax, isa_type: event.target.value })}><option value="general">{t("일반형")}</option><option value="preferential">{t("서민형·농어민형")}</option></select></label>}</div><div className="command-row"><button className="primary-button" type="button" disabled={busy} onClick={calculateTax}>{busy ? "계산 중…" : "세금 계산하기"}</button></div>{taxResult && <TaxResult response={taxResult} />}</article></section>;
  }

  return <FinanceAnalysis data={data} error={error} chartOnly={featureId.endsWith("chart")} />;
}

function ProductResult({ kind, response }: { kind: ProductKind; response: Record<string, any> }) {
  const result = (response.result ?? {}) as Record<string, any>;
  const rows = (result.alternatives ?? []) as Array<Record<string, any>>;
  const fields = kind === "loan" ? ["annual_rate", "total_cost", "monthly_payment"] : kind === "insurance" ? ["monthly_premium", "coverage_score"] : ["annual_rate", "expected_interest"];
  return <article className="panel legacy-product-result"><div className="panel-heading"><div><span className="eyebrow">COMPARISON RESULT</span><h2>{PRODUCT_LABELS[kind]}</h2></div><span className="count-badge">{rows.length}{t("개")}</span></div><p className="workspace-copy">{String(result.summary ?? "비교 결과")}</p>{rows.length ? <div className="legacy-product-table"><div className="legacy-product-row header"><span>{t("순위")}</span><span>{t("상품명")}</span><span>{t("제공사")}</span>{fields.map((field) => <span key={field}>{PRODUCT_FIELD_LABELS[field]}</span>)}</div>{rows.map((row, index) => <div className={`legacy-product-row${index === 0 ? " best" : ""}`} key={`${kind}-${String(row.name)}-${index}`}><span>{index + 1}</span><strong>{String(row.name ?? "상품")}</strong><span>{String(row.provider ?? "제공사 확인 필요")}</span>{fields.map((field) => <span key={field}>{displayValue(field, row[field])}</span>)}</div>)}</div> : <div className="empty-state">{t("조건에 맞는 비교 결과가 없습니다.")}</div>}</article>;
}

function TaxResult({ response }: { response: Record<string, any> }) {
  const result = (response.result ?? {}) as Record<string, any>;
  const scalarEntries = Object.entries(result).filter(([, value]) => ["string", "number", "boolean"].includes(typeof value));
  const scenarios = result.scenarios && typeof result.scenarios === "object" ? Object.entries(result.scenarios as Record<string, Record<string, unknown>>) : [];
  const suggestions = Array.isArray(result.suggestions) ? result.suggestions : [];
  return <section className="legacy-tax-result" aria-label={t("세금 계산 결과")}><div className="panel-heading"><div><span className="eyebrow">CALCULATION RESULT</span><h3>{t("세금 계산 결과")}</h3></div><span className="count-badge">{t("참고용")}</span></div><div className="metric-grid tax-metric-grid">{scalarEntries.filter(([key]) => !["message", "disclaimer"].includes(key)).map(([key, value]) => <div key={key}><span>{TAX_LABELS[key] ?? key.replaceAll("_", " ")}</span><strong>{displayValue(key, value)}</strong></div>)}</div>{scenarios.length > 0 && <div className="card-grid">{scenarios.map(([name, values]) => <article className="insight-card" key={name}><header><strong>{name}</strong></header><dl>{Object.entries(values).map(([key, value]) => <div key={key}><dt>{TAX_LABELS[key] ?? PRODUCT_FIELD_LABELS[key] ?? key.replaceAll("_", " ")}</dt><dd>{displayValue(key, value)}</dd></div>)}</dl></article>)}</div>}{suggestions.length > 0 && <div className="recommendation-list"><h3>{t("절세 점검 제안")}</h3>{suggestions.map((item: unknown, index: number) => <p key={index}>• {suggestionText(item)}</p>)}</div>}{result.message && <p className="inline-notice">{String(result.message)}</p>}<p className="workspace-copy">{String(result.disclaimer ?? "계산 결과는 참고용이며 실제 신고 결과와 다를 수 있습니다.")}</p></section>;
}

function FinanceAnalysis({ data, error, chartOnly }: { data: Record<string, any> | null; error: string; chartOnly: boolean }) {
  const monthlySavings = Object.entries(data?.monthly_savings ?? {}) as Array<[string, number]>;
  const spendingMap = useMemo(() => Object.fromEntries(Object.entries(data?.spending_trend ?? {})), [data]);
  const projection = (data?.projection ?? []) as number[];
  const basis = (data?.projection_basis ?? {}) as Record<string, any>;
  if (chartOnly) return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">12 MONTHS</span><h2>{t("고급 차트")}</h2></div></div><p className="workspace-copy">{t("저장된 기록의 월별 저축·지출 흐름과 12개월 예측을 표시합니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="trend-grid">{monthlySavings.map(([month, saving], index) => <div key={month}><span>{month}</span><strong>{money(saving)}{t("원")}</strong><small>{t("지출 ")}{money(spendingMap[month])}{t("원 · 예측 ")}{money(projection[index])}{t("원")}</small></div>)}</div>{!monthlySavings.length && <div className="empty-state">{t("차트를 만들 생활금융 기록이 없습니다.")}</div>}</article></section>;
  return <section className="data-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">PERSONAL FINANCE ANALYTICS</span><h2>{t("재무 분석")}</h2></div></div><p className="workspace-copy">{t("저장된 생활금융 기록만 계산합니다. 표본이 없으면 0원 기준이며 데모 수치를 만들지 않습니다.")}</p>{error && <div className="inline-notice error-text">{error}</div>}<div className="metric-grid"><div><span>{t("이번 달 수입")}</span><strong>{money(basis.monthly_income)}{t("원")}</strong></div><div><span>{t("이번 달 지출")}</span><strong>{money(basis.monthly_expenses)}{t("원")}</strong></div><div><span>{t("12개월 예상 누적")}</span><strong>{money(projection.at(-1))}{t("원")}</strong></div><div><span>{t("경고")}</span><strong>{Number(data?.alerts?.length ?? 0)}{t("건")}</strong></div></div></article><article className="panel"><div className="panel-heading"><div><span className="eyebrow">CATEGORY</span><h2>{t("지출 카테고리 분석")}</h2></div></div><div className="card-grid">{Object.entries(data?.category_stats ?? {}).map(([category, row]) => <section className="insight-card" key={category}><header><strong>{category}</strong><span>{Number((row as any).count ?? 0)}{t("건")}</span></header><dl><dt>{t("합계")}</dt><dd>{money((row as any).total)}{t("원")}</dd><dt>{t("평균")}</dt><dd>{money((row as any).avg)}{t("원")}</dd></dl></section>)}</div></article></section>;
}
