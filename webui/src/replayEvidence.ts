export interface ReplayCandle { time: number; open: number; high: number; low: number; close: number }
export interface ReplayTrade {
  entry_index: number; exit_index: number; side: "LONG" | "SHORT";
  entry_price: number; exit_price: number; exit_reason: string;
  gross_pnl_percent: number; cost_percent: number; net_pnl_percent: number;
}
export interface ReplayPoint { time: number; value: number; drawdown: number }
export interface ReplayEvidence { candles: ReplayCandle[]; trades: ReplayTrade[]; equity: ReplayPoint[]; hash: string }
const finite = (n: unknown): n is number => typeof n === "number" && Number.isFinite(n);

// Display-only formatting; stored replay prices and returns stay unchanged.
export function formatReplayPercent(value: number): string {
  if (!finite(value)) return "미기록";
  const rounded = Number(value.toFixed(4));
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(4)}%`;
}

export function formatReplayPrice(value: number): string {
  if (!finite(value)) return "미기록";
  const absolute = Math.abs(value);
  if (absolute > 0 && absolute < 1e-12) return value.toExponential(5);
  return value.toLocaleString("ko-KR", absolute > 0 && absolute < 1
    ? { maximumSignificantDigits: 6 }
    : { maximumFractionDigits: 2 });
}

export function replayPriceMinMove(minimum: number): number {
  return 10 ** -Math.min(12, Math.max(2, 5 - Math.floor(Math.log10(minimum))));
}

// Show all arrows but only the chosen trade's names. Count thresholds cannot
// prevent overlap when even a few trades cluster inside a small visible range.
export function replayMarkerText(id: string | undefined, text: string | undefined, selected: number | null): string {
  return selected !== null && id === String(selected) ? text ?? "" : "";
}

// Stored evidence only: never fetch today's candles or fabricate absent legacy fields.
export function readReplayEvidence(metrics: Record<string, any>, versionId: string): ReplayEvidence | null {
  const chart = metrics.replay_visualization;
  if (chart?.schema_version !== 1 || chart.status !== "available"
      || chart.basis !== "closed_trade_compounded_return"
      || chart.binding?.version_id !== versionId || chart.simulation_only !== true) return null;
  const { candles, equity } = chart;
  const trades = metrics.trades;
  if (!Array.isArray(candles) || !candles.length || candles.length > 5000
      || !Array.isArray(equity) || !equity.length || !Array.isArray(trades)
      || metrics.decisions !== trades.length || !finite(metrics.net_pnl_percent)) return null;
  if (candles.some((c, i) => !c || !Number.isInteger(c.time) || c.time <= 0
      || (i > 0 && c.time <= candles[i - 1].time)
      || ![c.open, c.high, c.low, c.close].every(v => finite(v) && v > 0)
      || c.low > Math.min(c.open, c.close) || c.high < Math.max(c.open, c.close))) return null;
  if (trades.some((t, i) => !t || !Number.isInteger(t.entry_index) || !Number.isInteger(t.exit_index)
      || t.entry_index < 0 || t.exit_index <= t.entry_index || t.exit_index >= candles.length
      || (i > 0 && t.entry_index <= trades[i - 1].exit_index)
      || !["LONG", "SHORT"].includes(t.side)
      || ![t.entry_price, t.exit_price].every(v => finite(v) && v > 0)
      || ![t.net_pnl_percent, t.gross_pnl_percent, t.cost_percent].every(finite))) return null;
  if (equity.some((p, i) => !p || !finite(p.time) || !finite(p.value) || !finite(p.drawdown)
      || (i > 0 && p.time <= equity[i - 1].time))) return null;
  if (equity[0].time !== candles[0].time || equity[0].value !== 0
      || equity.at(-1).time !== candles.at(-1).time
      || Math.abs(equity.at(-1).value - metrics.net_pnl_percent) > 0.00001) return null;
  if (trades.some((t, i) => equity[i + 1]?.time !== candles[t.exit_index].time
      || Math.abs(equity[i + 1]?.value - metrics.equity_curve_percent?.[i]) > 0.00001
      || !finite(metrics.equity_curve_percent?.[i]))) return null;
  return { candles, trades, equity, hash: String(chart.candles_sha256 ?? "") };
}

export function replayAction(side: "LONG" | "SHORT", entry: boolean, locale: 'ko' | 'en' = 'ko'): string {
  const buy = (side === "LONG") === entry;
  return `${buy ? "▲ BUY" : "▼ SELL"} · ${side} ${locale === 'en' ? (entry ? 'ENTRY' : 'EXIT') : (entry ? "진입" : "청산")}`;
}

export function replayExitReason(reason: string, locale: 'ko' | 'en' = 'ko'): string {
  if (locale === 'en') return ({stop_loss:'Stop loss',take_profit:'Take profit',declarative_exit:'Strategy exit condition',horizon:'Holding period ended'} as Record<string,string>)[reason] ?? 'Reason not recorded';
  return ({ stop_loss: "손절", take_profit: "익절", declarative_exit: "전략 청산 조건", horizon: "보유기간 종료" } as Record<string, string>)[reason] ?? "사유 미기록";
}
