import { useEffect, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  HistogramSeries,
  type UTCTimestamp,
} from "lightweight-charts";

import type { CandleSnapshot } from "../types";

export function MarketChart({ snapshot }: { snapshot: CandleSnapshot | null }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !snapshot?.candles.length) return;

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#0b1220" },
        textColor: "#91a2bd",
        panes: { separatorColor: "#26364f", separatorHoverColor: "#3a5275" },
      },
      grid: {
        vertLines: { color: "#17243a" },
        horzLines: { color: "#17243a" },
      },
      rightPriceScale: { borderColor: "#273853" },
      timeScale: { borderColor: "#273853", timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: "#5475a5" }, horzLine: { color: "#5475a5" } },
    });
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#20c997",
      downColor: "#ff5d73",
      wickUpColor: "#20c997",
      wickDownColor: "#ff5d73",
      borderVisible: false,
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

    candleSeries.setData(
      snapshot.candles.map((candle) => ({
        time: Math.floor(candle.open_time / 1000) as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
      })),
    );
    volumeSeries.setData(
      snapshot.candles.map((candle) => ({
        time: Math.floor(candle.open_time / 1000) as UTCTimestamp,
        value: candle.volume,
        color: candle.close >= candle.open ? "rgba(32,201,151,.35)" : "rgba(255,93,115,.35)",
      })),
    );
    chart.timeScale().fitContent();

    return () => chart.remove();
  }, [snapshot]);

  return <div className="market-chart" ref={containerRef} aria-label="BTCUSDT 공개 시장 캔들 차트" />;
}
