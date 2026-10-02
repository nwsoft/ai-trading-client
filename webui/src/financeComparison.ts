/** Local, illustrative cash-flow math. No quotes, eligibility, advice, IO or persistence. */
export type LoanMethod = 'annuity' | 'principal' | 'bullet';
export type SavingMethod = 'deposit' | 'installment';
export function numeric(raw: string, min: number, max: number, integer = false): number | null {
  if (!raw.trim() || !/^\d+(\.\d+)?$/.test(raw.trim())) return null;
  const value = Number(raw);
  return Number.isFinite(value) && value >= min && value <= max && (!integer || Number.isSafeInteger(value)) ? value : null;
}
export function loanEstimate(amountRaw: string, monthsRaw: string, rateRaw: string, feeRaw: string, method: LoanMethod) {
  const principal = numeric(amountRaw, 1, 1e12, true), months = numeric(monthsRaw, 1, 600, true);
  const rate = numeric(rateRaw, 0, 100), fees = numeric(feeRaw, 0, 1e12, true);
  if (principal === null || months === null || rate === null || !['annuity', 'principal', 'bullet'].includes(method)) return null;
  if (feeRaw.trim() && fees === null) return null;
  const r = rate / 1200;
  // expm1/log1p preserves very small non-zero rates.
  const fixed = r === 0 ? principal / months : principal * r / -Math.expm1(-months * Math.log1p(r));
  let balance = principal, interest = 0;
  const payments: number[] = [];
  for (let month = 1; month <= months; month++) {
    const cost = balance * r;
    const repaid = month === months ? balance : method === 'bullet' ? 0 : method === 'principal' ? principal / months : fixed - cost;
    payments.push(repaid + cost); interest += cost; balance = Math.max(0, balance - repaid);
  }
  return { principal, months, rate, fees, interest, first: payments[0], last: payments[months - 1],
    total: fees === null ? null : principal + interest + fees, cost: fees === null ? null : interest + fees, payments };
}
export function savingEstimate(amountRaw: string, monthsRaw: string, rateRaw: string, taxRaw: string, method: SavingMethod) {
  const amount = numeric(amountRaw, 1, 1e12, true), months = numeric(monthsRaw, 1, 600, true);
  const rate = numeric(rateRaw, 0, 100), taxRate = numeric(taxRaw, 0, 100);
  if (amount === null || months === null || rate === null || !['deposit', 'installment'].includes(method)) return null;
  if (taxRaw.trim() && taxRate === null) return null;
  const principal = method === 'deposit' ? amount : amount * months;
  if (principal > 1e12) return null;
  // Simple interest; installment is equal payments at each month's beginning.
  const interest = amount * rate / 1200 * (method === 'deposit' ? months : months * (months + 1) / 2);
  const tax = taxRate === null ? null : interest * taxRate / 100;
  return { principal, months, rate, taxRate, interest, tax, netInterest: tax === null ? null : interest - tax,
    maturity: tax === null ? null : principal + interest - tax };
}
