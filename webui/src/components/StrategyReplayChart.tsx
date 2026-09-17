import { useEffect, useMemo, useRef, useState } from "react";
import { CandlestickSeries, LineSeries, LineType, createChart, createSeriesMarkers,
  type IChartApi, type UTCTimestamp, type Time, type SeriesMarker, type ISeriesMarkersPluginApi } from "lightweight-charts";
import type { StrategyVersion } from "../types";
import { readReplayEvidence, replayAction, replayExitReason, formatReplayPrice as number,
  formatReplayPercent as percent, replayPriceMinMove, replayMarkerText, type ReplayEvidence } from "../replayEvidence";
const utc = (time: number) => new Date(time * 1000).toISOString().replace("T", " ").slice(0, 16);
const PAGE_SIZE = 20;

function ReplayView({ evidence, currency }: { evidence: ReplayEvidence; currency: string }) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const markerRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const allMarkers = useRef<SeriesMarker<UTCTimestamp>[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [page, setPage] = useState(0);
  const [chartError, setChartError] = useState(false);
  const { candles, trades, equity } = evidence;

  useEffect(() => {
    if (!container.current) return;
    let chart: IChartApi | undefined;
    setChartError(false);
    try {
      chart = createChart(container.current, {
        autoSize: true, height: 460,
        layout: { background: { color: "#0b1220" }, textColor: "#b8c8db" },
        grid: { vertLines: { color: "#17243a" }, horzLines: { color: "#17243a" } },
        timeScale: { timeVisible: true, secondsVisible: false },
        localization: { timeFormatter: (time: number | string | object) => typeof time === "number" ? `${utc(time)} UTC` : String(time) },
      });
      chartRef.current = chart;
      const minimum = Math.min(...candles.map(c => c.low));
      const price = chart.addSeries(CandlestickSeries, {
        upColor: "#20c997", downColor: "#ff5d73", wickUpColor: "#20c997", wickDownColor: "#ff5d73", borderVisible: false,
        priceFormat: { type: "custom", formatter: number, minMove: replayPriceMinMove(minimum) },
      });
      price.setData(candles.map(c => ({ ...c, time: c.time as UTCTimestamp })));
      const curve = chart.addSeries(LineSeries, {
        title: "청산 기준 누적 수익률", color: "#5bbcff", lineWidth: 2,
        // Custom formatter avoids the installed library's percent precision/scale
        // ambiguity. Axis, crosshair and trade details use the same percentage points.
        lineType: LineType.WithSteps, priceFormat: { type: "custom", formatter: percent, minMove: 0.0001 },
      }, 1);
      curve.setData(equity.map(p => ({ time: p.time as UTCTimestamp, value: p.value })));
      chart.panes()[1]?.setHeight(150);
      const markers: SeriesMarker<UTCTimestamp>[] = trades.flatMap((trade, i) => [true, false].map(entry => {
        const buy = (trade.side === "LONG") === entry;
        return { id: String(i), time: candles[entry ? trade.entry_index : trade.exit_index].time as UTCTimestamp,
          position: buy ? "belowBar" as const : "aboveBar" as const,
          color: buy ? "#20c997" : "#ff5d73", shape: buy ? "arrowUp" as const : "arrowDown" as const,
          text: `#${i + 1} ${replayAction(trade.side, entry)}` };
      })).sort((a, b) => Number(a.time) - Number(b.time));
      allMarkers.current = markers;
      markerRef.current = createSeriesMarkers(price, markers.map(m => ({ ...m, text: "" })));
      chart.subscribeClick(param => {
        if (typeof param.time !== "number") return;
        const i = trades.findIndex(t => candles[t.entry_index].time === param.time || candles[t.exit_index].time === param.time);
        if (i >= 0) { setSelected(i); setPage(Math.floor(i / PAGE_SIZE)); }
      });
      chart.timeScale().fitContent();
    } catch {
      setChartError(true);
      chart?.remove();
      chart = undefined;
      chartRef.current = null;
      markerRef.current = null;
    }
    return () => { chartRef.current = null; markerRef.current = null; chart?.remove(); };
  }, [evidence, candles, trades, equity]);

  useEffect(() => {
    markerRef.current?.setMarkers(allMarkers.current.map(m => ({ ...m,
      text: replayMarkerText(m.id, m.text, selected) })));
  }, [selected, evidence]);

  function selectTrade(i: number) {
    setSelected(i);
    const trade = trades[i];
    chartRef.current?.timeScale().setVisibleLogicalRange({ from: Math.max(0, trade.entry_index - 8), to: Math.min(candles.length - 1, trade.exit_index + 8) });
  }
  const selectedTrade = selected === null ? null : trades[selected];
  const pages = Math.max(1, Math.ceil(trades.length / PAGE_SIZE));
  return <>
    <div className="replay-toolbar"><span>상단: 가격 ({currency}) · 하단: 청산 기준 누적 수익률 (%)</span><button type="button" onClick={() => chartRef.current?.timeScale().fitContent()}>전체 구간</button></div>
    <div ref={container} className="strategy-replay-chart" aria-label="검증에 사용한 캔들, 진입·청산 타점 및 누적 수익률 차트" />
    {chartError && <p role="alert">차트 표시 실패 · 아래 저장된 거래 기록은 계속 확인할 수 있습니다.</p>}
    <p className="replay-note">차트와 시각은 UTC 캔들 시작 시각 기준입니다. 마커는 해당 봉의 모의 진입·청산이며 실제 체결 시각이 아닙니다. 초록 ▲ 매수 · 빨강 ▼ 매도. 전체 타점은 화살표로, 선택한 거래의 진입·청산 이름만 글자로 표시합니다. 거래 행을 선택하면 해당 구간으로 이동합니다.</p>
    <div className="replay-selection" aria-live="polite">{selectedTrade && selected !== null
      ? <>#{selected + 1} · {replayAction(selectedTrade.side, true)} {number(selectedTrade.entry_price)} → {replayAction(selectedTrade.side, false)} {number(selectedTrade.exit_price)} {currency}<br />{replayExitReason(selectedTrade.exit_reason)} · 비용 차감 수익률 {percent(selectedTrade.net_pnl_percent)}</>
      : trades.length ? "타점 또는 거래 행을 선택해 근거를 확인하세요." : "조건을 충족해 완료된 거래가 없습니다. 0% 선은 거래 없음이며 수익 검증 통과를 뜻하지 않습니다."}</div>
    {selectedTrade && <details className="replay-raw-values"><summary>선택 거래 계산 원본 값 보기</summary>
      <p>화면의 가격·수익률만 반올림하며 아래 저장된 계산 원본은 변경하지 않습니다.</p>
      <dl><dt>진입 가격 ({currency})</dt><dd>{String(selectedTrade.entry_price)}</dd>
        <dt>청산 가격 ({currency})</dt><dd>{String(selectedTrade.exit_price)}</dd>
        <dt>비용 차감 수익률 (%)</dt><dd>{String(selectedTrade.net_pnl_percent)}</dd></dl>
    </details>}
    <div className="replay-table-scroll"><table className="replay-table">
      <caption>과거재생 모의 거래 {trades.length}건 · 가격 {currency} · 시간 UTC · 손익은 거래별 수익률</caption>
      <thead><tr><th>거래</th><th>방향</th><th>진입 봉 / 가격</th><th>청산 봉 / 가격</th><th>청산 사유</th><th>비용 전</th><th>비용</th><th>비용 차감</th></tr></thead>
      <tbody>{trades.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((t, offset) => {
        const i = page * PAGE_SIZE + offset;
        return <tr key={i} className={selected === i ? "selected" : ""}>
          <td><button type="button" aria-pressed={selected === i} onClick={() => selectTrade(i)}>#{i + 1} 보기</button></td><td>{t.side}</td>
          <td>{utc(candles[t.entry_index].time)}<br /><span title={`계산 원본: ${t.entry_price} ${currency}`}>{number(t.entry_price)}</span></td>
          <td>{utc(candles[t.exit_index].time)}<br /><span title={`계산 원본: ${t.exit_price} ${currency}`}>{number(t.exit_price)}</span></td>
          <td>{replayExitReason(t.exit_reason)}</td><td>{percent(t.gross_pnl_percent)}</td><td>{percent(t.cost_percent)}</td>
          <td className={t.net_pnl_percent >= 0 ? "replay-gain" : "replay-loss"}>{percent(t.net_pnl_percent)}</td>
        </tr>;
      })}</tbody>
    </table></div>
    {pages > 1 && <div className="replay-toolbar"><button type="button" disabled={page === 0} onClick={() => setPage(p => p - 1)}>이전 거래</button><span>{page + 1} / {pages}</span><button type="button" disabled={page + 1 === pages} onClick={() => setPage(p => p + 1)}>다음 거래</button></div>}
  </>;
}

export function StrategyReplayChart({ version }: { version: StrategyVersion }) {
  const [open, setOpen] = useState(false);
  const validation = version.execution_validation;
  const metrics = validation?.metrics;
  const evidence = useMemo(() => metrics ? readReplayEvidence(metrics, version.version_id) : null, [metrics, version.version_id]);
  if (validation?.mode !== "historical_replay") return null;
  return <details className="strategy-replay" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>과거재생 차트 · 타점·누적 수익률·거래 내역</summary>
    {!evidence ? <p>이 결과에는 연결 가능한 원본 캔들·거래 근거가 없거나 기록이 일치하지 않습니다. 기존 버전의 요약은 보존됩니다. 규칙을 새 버전으로 저장·승인한 뒤 과거 시세 재생을 실행하면 새 근거를 생성할 수 있습니다.</p> : <>
      <p>{String(metrics.validation_source ?? metrics.exchange ?? metrics.broker ?? "기관 미기록").toUpperCase()} · {String(metrics.symbol ?? "종목 미기록")} · {String(metrics.validation_interval ?? "시간봉 미기록")} · 버전 {version.version}<br />검증 기록: {String(validation.recorded_at ?? "미기록")}</p>
      <p className="replay-note">비용 차감 후 거래별 수익률을 복리 연결한 모의 결과입니다. 보유 중 평가손익·실제 계좌 잔고·주문 수량·레버리지 성과가 아닙니다. 과거재생은 PAPER·LIVE 검증이나 여권 등급을 대체하지 않습니다.</p>
      {open && <ReplayView key={`${version.version_id}:${validation.recorded_at}`} evidence={evidence} currency={String(metrics.quote_currency ?? "가격 단위 미기록")} />}
      <p className="replay-note">동일 봉 익절·손절 동시 도달 시 손절 우선. 비용은 설정 기반 추정치이며 펀딩비·시장충격은 미반영입니다. 캔들 식별값은 로컬 데이터 대조용이며 외부 인증이 아닙니다. {evidence.hash.slice(0, 12)}</p>
    </>}
  </details>;
}
