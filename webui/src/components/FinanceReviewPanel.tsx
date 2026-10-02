import { useState } from "react";

type Review = Record<string, any>;
const money = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? `${value.toLocaleString()}원` : "기록 없음";

export function FinanceReviewPanel({ review, onAsk, onOpenFinance }: {
  review?: Review; onAsk?: (question: string) => void; onOpenFinance?: () => void;
}) {
  return <article className="panel finance-review-panel">
    <div className="panel-heading"><div><span className="eyebrow">MY FINANCIAL CONTEXT</span><h2>이번 달 내 돈 점검</h2></div><span className="state-pill">로컬 기록 · 판단 보조</span></div>
    {!review ? <p role="status">생활금융 기록을 확인 중입니다.</p> : <>
      <p className="workspace-copy">{review.period_start ?? "기간 미확인"} ~ {review.period_end ?? "기준일 미확인"} · KRW · 마지막 기록 {review.latest_record_date ?? "없음"}</p>
      <div className="metric-grid life-finance-kpi-grid">
        <div><span>등록 수입</span><strong>{money(review.income)}</strong></div>
        <div><span>등록 지출</span><strong>{money(review.expense)}</strong></div>
        <div><span>기록상 수입−지출</span><strong>{money(review.recorded_difference)}</strong></div>
      </div>
      <p className="workspace-copy">{review.boundary ?? "생활금융 자료를 확인하지 못했습니다. 계좌 평가와 별개입니다."}</p>
      <ul>{(review.actions ?? []).map((action: string) => <li key={action}>{action}</li>)}</ul>
      {review.transfer_count > 0 && <p>내 계좌 이체 {review.transfer_count}건 · {money(review.transfer_amount)} — 수입·소비에서 제외</p>}
      {!!review.top_expenses?.length && <div className="weight-list" aria-label="등록 지출 비중">{review.top_expenses.map((row: Review) => <div key={row.category}><span>{row.category}</span><progress aria-label={`${row.category} 비중`} max={review.expense} value={row.amount} /><strong>{money(row.amount)}</strong></div>)}</div>}
    </>}
    <div className="command-row">
      {onAsk && <button type="button" className="secondary-button" onClick={() => onAsk("이번 달 등록된 생활금융 기록의 수입·지출·내 계좌 이체와 목표를 구분해 설명해줘. 누락 자료와 다음 확인 사항을 알려주고, 기록상 차액을 계좌 잔액이나 투자 가능액으로 판단하지 마.")}>이 점검을 AI에게 질문</button>}
      {onOpenFinance && <button type="button" className="secondary-button" onClick={onOpenFinance}>생활금융 기록·계획 열기</button>}
    </div>
    {onAsk && <small className="workspace-copy">질문 초안만 엽니다. 전송과 외부 AI 사용은 어시스턴트에서 직접 선택합니다.</small>}
  </article>;
}

export function MonthlyPlanCalculator() {
  const [draft, setDraft] = useState({income: "", expense: "", debt: "", goal: ""});
  const fields = [["income", "예상 월 수입"], ["expense", "월 생활비·보험료 (대출 상환·목표 적립 제외)"], ["debt", "월 대출 상환액 (원금+이자)"], ["goal", "월 목표 적립액"]] as const;
  const values = fields.map(([key]) => draft[key].trim() === "" ? NaN : Number(draft[key]));
  const valid = values.every(value => Number.isSafeInteger(value) && value >= 0 && value <= 1e12);
  const [income, expense, debt, goal] = values;
  const balance = valid ? income - expense - debt - goal : null;
  const stress = valid ? Math.round(income * .8) - expense - debt - goal : null;
  return <article className="panel finance-review-panel">
    <div className="panel-heading"><h2>수입이 줄면 어떻게 달라질까?</h2><span className="state-pill">입력 가정 · 무저장 계산</span></div>
    <p className="workspace-copy">월중 가계부에서 월 수입을 추정하지 않습니다. 원 단위로 직접 입력하세요. 없는 항목은 0을 입력하고, 같은 지출을 생활비·상환액·적립액에 중복 입력하지 마세요.</p>
    <div className="form-grid">{fields.map(([key, label]) => <label key={key}>{label}<input type="number" min="0" max="1000000000000" step="1" value={draft[key]} onChange={event => setDraft({...draft, [key]: event.target.value})} /></label>)}</div>
    <div className="metric-grid" aria-live="polite"><div><span>기본 계획 차액</span><strong>{balance === null ? "입력 필요" : money(balance)}</strong></div><div><span>수입 20% 감소 시 차액</span><strong>{stress === null ? "입력 필요" : money(stress)}</strong></div></div>
    {balance !== null && <p>{balance < 0 ? "입력한 계획에서 월 부족액이 발생합니다." : "양수 차액도 투자 가능액이 아닙니다."} 예상 수입−생활비−대출 상환−목표 적립으로 계산하며, 기존 잔액·추가 세금·비정기 지출은 포함하지 않습니다.</p>}
    <p className="workspace-copy">실제 이체·대출 심사·투자·목표 저장을 실행하지 않습니다. 입력값은 외부로 전송하지 않습니다.</p>
  </article>;
}
