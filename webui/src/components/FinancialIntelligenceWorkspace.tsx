import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type { GatewayClient } from "../api";

type Service = "blockchain" | "stock" | "ai_analyst";
type Action = "market" | "events" | "narrative" | "macro" | "fundamental" | "valuation" | "screener" | "technical" | "backtest" | "institutional";
type TabContract = { label: string; action: Action; title: string; description: string; guide: string; button: string };

const TABS: Record<Service, TabContract[]> = {
  ai_analyst: [
    { label: "글로벌 시장", action: "market", title: "시장 현황과 수익률", description: "주요 지수·종목·환율·원자재·가상자산의 가격, 기간 수익률, 변동성과 출처를 차트와 함께 확인합니다.", guide: "프리셋 선택 → 시장 현황 조회 → 출처·기준시각 → 수익률·변동성 순으로 확인", button: "시장 현황 조회" },
    { label: "이벤트·속보", action: "events", title: "보유자산 일정과 속보", description: "연결된 일정·뉴스 공급자에서 보유자산과 관련된 항목을 우선 표시합니다.", guide: "일정·속보 확인 → 보유자산 관련 항목 → 발생 시각·출처 → 예상 영향 확인", button: "일정·속보 확인" },
    { label: "내러티브", action: "narrative", title: "시장 내러티브", description: "반복 기사를 제거하고 보유자산·주제·파급력 기준으로 시장의 주요 이야기를 정리합니다.", guide: "내러티브 확인 → 반복 이슈 → 관련 자산 → 사실과 시장 해석을 분리해 확인", button: "내러티브 확인" },
    { label: "산업·거시", action: "macro", title: "산업·거시경제", description: "성장·물가·유동성·신용·금리 데이터로 현재 경기 국면과 자산군 영향을 설명합니다.", guide: "거시 환경 확인 → 경기 국면 → 자산군 영향 → 데이터 연결 상태 확인", button: "거시 환경 확인" },
  ],
  stock: [
    { label: "시장·섹터", action: "market", title: "시장 현황과 수익률", description: "주요 지수·종목·환율·원자재의 가격, 기간 수익률, 변동성과 출처를 확인합니다.", guide: "프리셋 선택 → 시장 현황 조회 → 출처·기준시각 → 수익률·변동성 순으로 확인", button: "시장 현황 조회" },
    { label: "기업 분석", action: "fundamental", title: "기업 재무분석", description: "기업 식별값을 입력하면 설정된 DART·SEC 공시 공급자에서 재무 데이터를 가져옵니다.", guide: "DART/SEC 선택 → 기업 식별값·연도 입력 → 공시 재무 분석 → 출처 확인", button: "공시 재무 분석" },
    { label: "가치평가", action: "valuation", title: "기업 가치평가", description: "현금흐름과 주식 수를 이용해 보수·기준·낙관 시나리오 범위를 계산합니다.", guide: "현금흐름·주식 수·순부채 입력 → 시나리오 계산 → 가정별 범위를 비교", button: "시나리오 계산" },
    { label: "종목 탐색", action: "screener", title: "종목 조건 검색", description: "관심 종목과 최소 가격을 입력해 공개 시세 기준 후보를 정리합니다.", guide: "관심 종목을 쉼표로 입력 → 최소 가격 설정 → 조건 검색 → 후보를 추가 검토", button: "조건 검색" },
    { label: "지표 탐색", action: "technical", title: "기술지표", description: "가격과 RSI·MACD·이동평균·볼린저밴드를 함께 계산합니다.", guide: "종목 입력 → 지표 조회 → 차트와 RSI·MACD·이동평균의 방향·충돌을 함께 확인", button: "지표 조회" },
    { label: "전략 검증", action: "backtest", title: "전략 검증", description: "과거 시세에 수수료·슬리피지·다음 봉 체결을 반영해 작동 여부를 검증합니다.", guide: "종목·빠른/느린 평균 입력 → 전략 검증 실행 → 거래 수·비용·MDD를 함께 확인", button: "전략 검증 실행" },
    { label: "기관 동향", action: "institutional", title: "기관 보유 변화", description: "허가된 기관 공시 공급자가 연결되면 신규 편입·비중 확대·축소를 표시합니다.", guide: "기관 동향 확인 → 신규·확대·축소 → 공시 기준일과 데이터 연결 상태 확인", button: "기관 동향 확인" },
  ],
  blockchain: [
    { label: "시장·섹터", action: "market", title: "시장 현황과 수익률", description: "가상자산의 가격, 기간 수익률, 변동성과 출처를 차트와 함께 확인합니다.", guide: "프리셋 선택 → 시장 현황 조회 → 출처·기준시각 → 수익률·변동성 순으로 확인", button: "시장 현황 조회" },
    { label: "코인 탐색", action: "screener", title: "종목 조건 검색", description: "여러 코인을 조건으로 비교해 추가 검토할 후보를 찾습니다.", guide: "관심 코인을 쉼표로 입력 → 최소 가격 설정 → 조건 검색 → 후보를 추가 검토", button: "조건 검색" },
    { label: "지표 탐색", action: "technical", title: "기술지표", description: "가격과 RSI·MACD·이동평균·볼린저밴드를 함께 계산합니다.", guide: "코인 입력 → 지표 조회 → 차트와 RSI·MACD·이동평균의 방향·충돌을 함께 확인", button: "지표 조회" },
    { label: "전략 검증", action: "backtest", title: "전략 검증", description: "과거 시세에 수수료·슬리피지·다음 봉 체결을 반영해 작동 여부를 검증합니다.", guide: "코인·빠른/느린 평균 입력 → 전략 검증 실행 → 거래 수·비용·MDD를 함께 확인", button: "전략 검증 실행" },
    { label: "이벤트·속보", action: "events", title: "보유자산 일정과 속보", description: "연결된 일정·뉴스 공급자에서 보유자산 관련 항목을 우선 표시합니다.", guide: "일정·속보 확인 → 보유자산 관련 항목 → 발생 시각·출처 → 예상 영향 확인", button: "일정·속보 확인" },
  ],
};

const MARKET_PRESETS: Record<string, Array<{ symbol: string; asset_type: string }>> = {
  "주요 시장": [
    { symbol: "^KS11", asset_type: "index" }, { symbol: "^GSPC", asset_type: "index" },
    { symbol: "^IXIC", asset_type: "index" }, { symbol: "KRW=X", asset_type: "fx" },
    { symbol: "GC=F", asset_type: "commodity" },
  ],
  "국내 시장": [
    { symbol: "^KS11", asset_type: "index" }, { symbol: "^KQ11", asset_type: "index" },
    { symbol: "005930.KS", asset_type: "stock" }, { symbol: "000660.KS", asset_type: "stock" },
  ],
  "미국 시장": [
    { symbol: "^GSPC", asset_type: "index" }, { symbol: "^IXIC", asset_type: "index" },
    { symbol: "AAPL", asset_type: "stock" }, { symbol: "MSFT", asset_type: "stock" },
  ],
  "가상자산": [
    { symbol: "BTC", asset_type: "crypto" }, { symbol: "ETH", asset_type: "crypto" },
    { symbol: "SOL", asset_type: "crypto" },
  ],
};

const LABELS: Record<string, string> = {
  status: "상태", message: "안내", error: "오류 안내", reason: "판단 근거", symbol: "종목", asset_type: "자산군",
  price: "현재가", returns: "기간 수익률", volatility_annualized: "연환산 변동성", as_of: "기준 시각", source: "출처",
  source_url_or_id: "출처 식별값", summaries: "시장 요약", errors: "수집 오류", events: "주요 일정", matched: "보유자산 관련 일정",
  news: "주요 뉴스", narratives: "시장 내러티브", macro: "거시 환경", industry: "산업 분석", fundamentals: "재무 분석",
  valuation: "가치평가", metrics: "핵심 지표", risk_signals: "위험 신호", quality_flags: "데이터 품질 안내", performance: "성과",
  exposure: "보유 비중", total_trades: "거래 수", trades: "거래 수", wins: "수익 거래", losses: "손실 거래", win_rate: "승률",
  total_return: "총 수익률", net_pnl: "순손익", fees: "수수료", max_drawdown: "최대 낙폭", profit_factor: "수익 팩터",
  expectancy: "거래당 기대값", sharpe: "샤프 지수", sortino: "소르티노 지수", generated_at: "생성 시각", captured_at: "수집 시각",
  direct_trade_signal: "직접 주문 신호", order_submitted: "주문 제출", auto_apply: "자동 적용", current_period: "현재 기준 기간",
  currency: "통화", periods: "기간별 재무", revenue: "매출", operating_income: "영업이익", net_income: "당기순이익", assets: "자산",
  liabilities: "부채", equity: "자본", operating_cash_flow: "영업현금흐름", capital_expenditure: "자본적 지출", free_cash_flow: "잉여현금흐름",
  revenue_growth_percent: "매출 성장률", operating_income_growth_percent: "영업이익 성장률", net_income_growth_percent: "순이익 성장률",
  operating_margin_percent: "영업이익률", net_margin_percent: "순이익률", roe_percent: "자기자본이익률", debt_to_equity: "부채비율",
  fcf_margin_percent: "잉여현금흐름률", cash_conversion: "현금 전환율", value_per_share: "주당 평가가치", enterprise_value: "기업가치",
  equity_value: "주주가치", bear: "보수 시나리오", base: "기준 시나리오", bull: "낙관 시나리오", assumptions: "계산 가정",
  projected: "연도별 추정", terminal_value: "영구가치", terminal_present_value: "영구가치 현재가치", changes: "보유 변화", action: "변화 구분",
  current_weight: "현재 비중", previous_weight: "이전 비중", weight_change: "비중 변화", filing_date: "공시일", report_period: "보고 기간",
  data_delay_warning: "공시 시차 주의", is_realtime_signal: "실시간 주문 신호", conditions: "조건", eligible: "조건 충족", available_cash: "가용 현금",
  risk_budget: "위험 예산", required_amount: "필요 금액",
  count: "시세 표본", rsi14: "RSI(14)", ma20: "20일 이동평균", ma50: "50일 이동평균", volume_ratio20: "20일 평균 대비 거래량",
  signals: "신호 요약", conflict: "지표 충돌", middle: "중심선", upper: "상단선", lower: "하단선", position: "밴드 내 위치",
  sector: "시장·섹터", provenance: "데이터 출처", timezone: "기준 시간대", freshness: "데이터 시차", is_delayed: "지연 시세",
  screen_reasons: "통과 조건", screen_score: "검색 점수", data_sufficient: "데이터 충분", initial_cash: "초기 자산", final_equity: "최종 평가액",
  equity_curve: "자산 곡선", rejected_orders: "거절 주문", gross_profit: "총이익", gross_loss: "총손실",
  avg_pnl: "거래당 평균 손익", max_drawdown_amount: "최대 낙폭", total_fees: "총비용",
};

const HIDDEN_RESULT_KEYS = new Set(["schema_version", "service", "action", "chart_points", "model_version", "rule_version", "inputs"]);

function friendlyLabel(key: string) {
  if (LABELS[key]) return LABELS[key];
  if (/[가-힣]/.test(key)) return key;
  return "세부 정보";
}

function displayValue(value: unknown, key = "") {
  if (value == null || value === "") return "-";
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "number") {
    const formatted = value.toLocaleString(undefined, { maximumFractionDigits: 4 });
    return key.includes("percent") || key === "win_rate" || key === "total_return" || key === "max_drawdown" ? `${formatted}%` : formatted;
  }
  const statusLabels: Record<string, string> = { ok: "정상", no_data: "데이터 없음", insufficient_data: "표본 부족", configuration_required: "데이터 연결 필요", error: "확인 필요" };
  return statusLabels[String(value)] ?? String(value);
}

type ChartSeries = { label: string; values: number[]; color: string };

function LineChart({ points = [], series, title = "가격 흐름", valueSuffix = "" }: { points?: Array<Record<string, any>>; series?: ChartSeries[]; title?: string; valueSuffix?: string }) {
  const baseValues = points.map((point) => Number(point.close ?? point.price ?? point.value)).filter((value) => Number.isFinite(value));
  const renderedSeries = (series?.length ? series : [{ label: title, values: baseValues, color: "#3b82f6" }]).filter((item) => item.values.length);
  const values = renderedSeries.flatMap((item) => item.values).filter((value) => Number.isFinite(value));
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 0;
  const span = Math.max(max - min, 1);
  const pathFor = (chartValues: number[]) => chartValues.map((value, index) => {
    const x = chartValues.length <= 1 ? 52 : 52 + (index / (chartValues.length - 1)) * 920;
    const y = 156 - ((value - min) / span) * 124;
    return `${index ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(" ");
  const format = (value: number) => `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${valueSuffix}`;
  return <div className="intelligence-chart-shell" aria-label={title}>
    <header><div><b>{title}</b><span>{values.length ? `${format(values.at(-1) ?? 0)} · 최저 ${format(min)} · 최고 ${format(max)}` : "조회 결과 없음"}</span></div><div className="chart-legend">{renderedSeries.map((item) => <span key={item.label}><i style={{ background: item.color }} />{item.label}</span>)}</div></header>
    <div className="legacy-intelligence-chart">{renderedSeries.length ? <svg viewBox="0 0 1000 180" preserveAspectRatio="none" role="img" aria-label={title}>
      {[0, 1, 2, 3].map((row) => <line key={row} x1="52" x2="972" y1={32 + row * 41.3} y2={32 + row * 41.3} className="chart-grid-line" />)}
      <text x="4" y="37">{format(max)}</text><text x="4" y="158">{format(min)}</text>
      {renderedSeries.map((item) => <path key={item.label} d={pathFor(item.values)} style={{ stroke: item.color }} />)}
    </svg> : <span>조회하면 검증 가능한 시계열이 여기에 표시됩니다.</span>}</div>
  </div>;
}

function periodValue(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function sourceName(row: Record<string, any>) {
  const provenance = (row.provenance ?? {}) as Record<string, any>;
  return String(provenance.source ?? row.source ?? "출처 미확인").replaceAll("_", " ");
}

function ResultTable({ headers, rows }: { headers: string[]; rows: Array<Array<ReactNode>> }) {
  return <div className="intelligence-table-scroll"><div className="intelligence-table" style={{ gridTemplateColumns: `repeat(${headers.length}, minmax(110px, 1fr))` }}>{headers.map((header) => <b key={header}>{header}</b>)}{rows.flatMap((row, rowIndex) => row.map((cell, cellIndex) => <span key={`${rowIndex}-${cellIndex}`}>{cell}</span>))}</div></div>;
}

function MarketResult({ payload, points }: { payload: Record<string, any>; points: Array<Record<string, any>> }) {
  const market = (payload.market ?? payload) as Record<string, any>;
  const summaries = (market.summaries ?? []) as Array<Record<string, any>>;
  return <div className="intelligence-result-view">
    <LineChart points={points} title={summaries[0]?.symbol ? `${summaries[0].symbol} 가격 흐름` : "시장 가격 흐름"} />
    <section className="intelligence-result-section"><header><h3>시장 요약</h3><span>{summaries.length}개 자산 · 기준시각과 출처 포함</span></header>
      {summaries.length ? <ResultTable headers={["종목", "자산군", "현재가", "1일", "1주", "1개월", "연환산 변동성", "기준 시각", "출처"]} rows={summaries.map((row) => [<strong>{row.symbol}</strong>, row.asset_type, displayValue(row.price), periodValue(row.returns?.["1D"]), periodValue(row.returns?.["1W"]), periodValue(row.returns?.["1M"]), periodValue(row.volatility_annualized), String(row.as_of ?? "-").replace("T", " ").slice(0, 19), sourceName(row)])} /> : <div className="honest-empty-state"><b>표시할 시장 시세가 없습니다.</b><span>공개 시세 연결 상태와 종목 코드를 확인하세요.</span></div>}
    </section>
  </div>;
}

function ScreenerResult({ payload }: { payload: Record<string, any> }) {
  const rows = (payload["조건 통과 종목"] ?? payload.matched ?? []) as Array<Record<string, any>>;
  const errors = (payload["수집 오류"] ?? payload.errors ?? []) as Array<Record<string, any>>;
  return <div className="intelligence-result-view"><section className="intelligence-result-section"><header><h3>조건 통과 후보</h3><span>가격 조건을 통과한 {rows.length}개 자산</span></header>{rows.length ? <>
    <div className="candidate-rank-list">{rows.map((row, index) => <article key={`${row.symbol}-${index}`}><b>{index + 1}</b><div><strong>{row.symbol}</strong><span>{row.asset_type} · {row.status === "ok" ? "시세 정상" : displayValue(row.status)}</span></div><div><span>현재가</span><strong>{displayValue(row.price)}</strong></div><div><span>1개월</span><strong className={Number(row.returns?.["1M"]) >= 0 ? "positive" : "negative"}>{periodValue(row.returns?.["1M"])}</strong></div><div><span>연환산 변동성</span><strong>{periodValue(row.volatility_annualized)}</strong></div><small>{sourceName(row)}</small></article>)}</div>
  </> : <div className="honest-empty-state"><b>조건을 통과한 후보가 없습니다.</b><span>입력 종목, 최소 가격, 공개 시세 연결 상태를 확인하세요.</span></div>}</section>{errors.length > 0 && <section className="intelligence-result-section warning-section"><header><h3>수집하지 못한 종목</h3><span>{errors.length}건</span></header>{errors.map((row, index) => <p key={index}>{row.symbol ?? "종목"}: {row.error ?? "시세 수집 실패"}</p>)}</section>}</div>;
}

function movingAverage(values: number[], period: number) {
  return values.map((_, index) => index + 1 < period ? Number.NaN : values.slice(index + 1 - period, index + 1).reduce((sum, value) => sum + value, 0) / period).filter(Number.isFinite);
}

function rsiSeries(values: number[], period = 14) {
  return values.map((_, index) => {
    if (index < period) return Number.NaN;
    const changes = values.slice(index - period, index + 1).slice(1).map((value, offset) => value - values[index - period + offset]);
    const gain = changes.reduce((sum, value) => sum + Math.max(value, 0), 0) / period;
    const loss = changes.reduce((sum, value) => sum + Math.max(-value, 0), 0) / period;
    return loss <= 1e-12 ? 100 : 100 - (100 / (1 + gain / loss));
  }).filter(Number.isFinite);
}

function TechnicalResult({ payload }: { payload: Record<string, any> }) {
  const points = (payload.chart_points ?? []) as Array<Record<string, any>>;
  const prices = points.map((point) => Number(point.close ?? point.price)).filter(Number.isFinite);
  const signals = (payload.signals ?? {}) as Record<string, any>;
  const macd = (payload.macd ?? {}) as Record<string, any>;
  const bollinger = (payload.bollinger ?? {}) as Record<string, any>;
  const metrics = [
    ["현재가", displayValue(payload.price)], ["RSI(14)", displayValue(payload.rsi14)], ["MACD", displayValue(macd.macd)], ["MACD 히스토그램", displayValue(macd.histogram)],
    ["20일 이동평균", displayValue(payload.ma20)], ["50일 이동평균", displayValue(payload.ma50)], ["볼린저 밴드 위치", displayValue(bollinger.position)], ["거래량 비율", displayValue(payload.volume_ratio20)],
  ];
  return <div className="intelligence-result-view"><div className="technical-chart-grid"><LineChart title={`${payload["종목"] ?? "종목"} 가격·이동평균`} series={[{ label: "종가", values: prices, color: "#3b82f6" }, { label: "MA20", values: movingAverage(prices, 20), color: "#22c55e" }, { label: "MA50", values: movingAverage(prices, 50), color: "#f59e0b" }]} /><LineChart title="RSI(14) 흐름" valueSuffix="" series={[{ label: "RSI", values: rsiSeries(prices), color: "#a78bfa" }]} /></div><section className="intelligence-result-section"><header><h3>지표 판독</h3><span>{payload.count ?? prices.length}개 시세 표본</span></header><div className="indicator-metric-grid">{metrics.map(([label, value]) => <div key={label}><span>{label}</span><strong>{value}</strong></div>)}</div><div className="signal-strip"><span>RSI <b>{signals.rsi ?? "-"}</b></span><span>MACD <b>{signals.macd ?? "-"}</b></span><span>추세 <b>{signals.trend ?? "-"}</b></span><span className={payload.conflict ? "negative" : "positive"}>신호 {payload.conflict ? "충돌 있음" : "정합"}</span></div></section></div>;
}

function BacktestResult({ payload }: { payload: Record<string, any> }) {
  const curve = (payload.equity_curve ?? []).map(Number).filter(Number.isFinite);
  const metrics = (payload.metrics ?? {}) as Record<string, any>;
  const assumptions = (payload.assumptions ?? {}) as Record<string, any>;
  return <div className="intelligence-result-view"><LineChart title="검증 자산 곡선" series={[{ label: "평가액", values: curve, color: "#22c55e" }]} /><section className="intelligence-result-section"><header><h3>검증 결과</h3><span>실제 주문을 만들지 않는 과거 시세 계산</span></header><div className="indicator-metric-grid"><div><span>최종 평가액</span><strong>{displayValue(payload.final_equity)}</strong></div><div><span>총 수익률</span><strong>{periodValue(Number(payload.total_return) * 100)}</strong></div><div><span>거래 수</span><strong>{displayValue(metrics.total_trades ?? payload.trades?.length ?? 0)}</strong></div><div><span>승률</span><strong>{periodValue(Number(metrics.win_rate ?? 0) * (Number(metrics.win_rate ?? 0) <= 1 ? 100 : 1))}</strong></div><div><span>순손익</span><strong>{displayValue(metrics.net_pnl ?? Number(payload.final_equity ?? 0) - Number(payload.initial_cash ?? 0))}</strong></div><div><span>최대 낙폭</span><strong>{displayValue(metrics.max_drawdown ?? metrics.max_drawdown_amount)}</strong></div><div><span>수수료율</span><strong>{periodValue(Number(assumptions.fee_rate ?? 0) * 100)}</strong></div><div><span>슬리피지</span><strong>{displayValue(assumptions.slippage_bps)} bps</strong></div></div></section></div>;
}

function ResultView({ action, payload, marketPoints }: { action: Action; payload: Record<string, any>; marketPoints: Array<Record<string, any>> }) {
  if (action === "market") return <MarketResult payload={payload} points={marketPoints} />;
  if (action === "screener") return <ScreenerResult payload={payload} />;
  if (action === "technical") return <TechnicalResult payload={payload} />;
  if (action === "backtest") return <BacktestResult payload={payload} />;
  if (payload.status === "configuration_required") return <div className="connection-required-state"><span>준비 중</span><h3>{payload.message ?? "운영 데이터 공급자 연결이 필요합니다."}</h3><p>이 화면은 임의 뉴스나 일정을 만들지 않습니다. 운영 관리자가 금융 인텔리전스의 RSS·일정·공시 공급자를 연결하면 같은 탭에서 자동으로 조회됩니다.</p><small>일반 사용자 설정 화면에서 연결하는 항목은 아니며, 현재 단계에서는 조회 UI만 준비되어 있고 실제 주문과 연결되지 않습니다.</small></div>;
  return <HumanResult value={payload} label="조회 결과 세부정보" />;
}

function HumanResult({ value, label, fieldKey = "" }: { value: unknown; label?: string; fieldKey?: string }) {
  if (Array.isArray(value)) {
    return <section className="human-result-group"><h3>{label}</h3>{value.length ? <div className="human-result-list">{value.map((item, index) => <HumanResult key={index} value={item} label={`${index + 1}번째 항목`} />)}</div> : <div className="honest-empty-state"><span>표시할 데이터가 없습니다.</span></div>}</section>;
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>).filter(([key]) => !HIDDEN_RESULT_KEYS.has(key) && !key.startsWith("_"));
    return <section className="human-result-group">{label && <h3>{label}</h3>}{entries.length ? <div className="human-result-grid">{entries.map(([key, item]) => item && typeof item === "object" ? <HumanResult key={key} value={item} label={friendlyLabel(key)} fieldKey={key} /> : <div className="human-result-field" key={key}><span>{friendlyLabel(key)}</span><strong>{displayValue(item, key)}</strong></div>)}</div> : <div className="honest-empty-state"><span>표시할 데이터가 없습니다.</span></div>}</section>;
  }
  return <div className="human-result-field"><span>{label ?? "결과"}</span><strong>{displayValue(value, fieldKey)}</strong></div>;
}

function compactEvidence(row: Record<string, any>) {
  const text = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";
  const source = text(row.exchange ?? row.broker ?? row.source).toUpperCase();
  const asset = text(row.symbol ?? row.ticker ?? row.asset ?? row.coin);
  const decision = text(row.decision ?? row.action ?? row.signal ?? row.status ?? row.result).replaceAll("_", " ");
  const reason = text(row.summary ?? row.reason ?? row.message ?? row.analysis).replace(/\s+/g, " ").slice(0, 220);
  const time = text(row.created_at ?? row.timestamp ?? row.executed_at ?? row.updated_at).replace("T", " ").slice(0, 19);
  return { source, asset, decision, reason, time };
}

function CompactEvidence({ row }: { row: Record<string, any> }) {
  const item = compactEvidence(row);
  return <div className="human-result-field compact-evidence">
    <span>{[item.time, item.source, item.asset].filter(Boolean).join(" · ") || "저장된 계정 근거"}</span>
    <strong>{item.decision || item.reason || "세부 판단 근거는 원본 기록에서 확인할 수 있습니다."}</strong>
    {item.decision && item.reason && <small>{item.reason}</small>}
  </div>;
}

function Summary({ snapshot }: { snapshot: Record<string, any> | null }) {
  const summary = (snapshot?.summary ?? {}) as Record<string, any>;
  const evidence = (snapshot?.evidence ?? {}) as Record<string, Array<Record<string, any>>>;
  const groups = [["AI 판단", evidence.ai_decisions ?? []], ["AI 분석", evidence.ai_analysis ?? []], ["위험 근거", evidence.risk ?? []], ["실행 결과", evidence.execution ?? []]] as const;
  return <section className="data-workspace ai-summary-workspace"><article className="panel"><div className="panel-heading"><div><span className="eyebrow">근거 기반 요약</span><h2>AI 요약 리포트</h2></div></div><p className="workspace-copy">AI 판단·분석·위험·실행 근거를 분리해 현재 계정의 기록만 요약합니다. 내부 테이블명이나 원시 JSON은 사용자 화면에 표시하지 않습니다.</p><div className="metric-grid human-summary-metrics"><div><span>AI 판단 근거</span><strong>{Number(summary.decision_count ?? 0).toLocaleString()}건</strong></div><div><span>분석 기록</span><strong>{Number(summary.analysis_count ?? 0).toLocaleString()}건</strong></div><div><span>위험 기록</span><strong>{Number(summary.risk_count ?? 0).toLocaleString()}건</strong></div><div><span>데이터 상태</span><strong>{summary.data_status === "available" ? "근거 있음" : "표본 부족"}</strong></div></div><div className="human-evidence-sections">{groups.map(([title, rows]) => <article className="human-evidence-card" key={title}><header><h3>{title}</h3><span>{rows.length}건</span></header>{rows.length ? <div className="human-evidence-list">{rows.slice(0, 3).map((row, index) => <CompactEvidence key={index} row={row} />)}</div> : <div className="honest-empty-state"><span>저장된 {title} 기록이 없습니다.</span></div>}</article>)}</div></article></section>;
}

type IntelligenceCache = {
  active: string;
  fields: Record<string, string>;
  results: Partial<Record<Action, Record<string, any>>>;
  errors: Partial<Record<Action, string>>;
};
const INTELLIGENCE_CACHE = new WeakMap<GatewayClient, Partial<Record<Service, IntelligenceCache>>>();

function defaultFields(service: Service) {
  return { market_preset: service === "blockchain" ? "가상자산" : "주요 시장", asset_type: service === "blockchain" ? "crypto" : "stock", symbols: service === "blockchain" ? "BTC,ETH,SOL" : "AAPL,MSFT,005930.KS,000660.KS", symbol: service === "blockchain" ? "BTC" : "AAPL", min_price: "0", fast: "5", slow: "20", provider: "DART", code: "", year: String(new Date().getFullYear()), base_fcf: "10000000000", shares: "100000000", net_debt: "0" };
}

function readCache(client: GatewayClient, service: Service): IntelligenceCache {
  const cached = INTELLIGENCE_CACHE.get(client)?.[service];
  return cached ?? { active: TABS[service][0].label, fields: defaultFields(service), results: {}, errors: {} };
}

function writeCache(client: GatewayClient, service: Service, value: IntelligenceCache) {
  const current = INTELLIGENCE_CACHE.get(client) ?? {};
  INTELLIGENCE_CACHE.set(client, { ...current, [service]: value });
}

export function FinancialIntelligenceWorkspace({ client, service, summaryOnly = false, onAskAssistant }: { client: GatewayClient; service: Service; summaryOnly?: boolean; onAskAssistant?: (question: string) => void }) {
  const tabs = TABS[service];
  const initialCache = useMemo(() => readCache(client, service), [client, service]);
  const [snapshot, setSnapshot] = useState<Record<string, any> | null>(null);
  const [active, setActive] = useState(initialCache.active);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<Partial<Record<Action, string>>>(initialCache.errors);
  const [results, setResults] = useState<Partial<Record<Action, Record<string, any>>>>(initialCache.results);
  const [fields, setFields] = useState<Record<string, string>>(initialCache.fields);
  useEffect(() => {
    const cached = readCache(client, service);
    setActive(cached.active); setFields(cached.fields); setResults(cached.results); setErrors(cached.errors);
    client.financialIntelligence(service).then(setSnapshot).catch((reason: unknown) => setErrors((current) => ({ ...current, [TABS[service][0].action]: reason instanceof Error ? reason.message : "금융 인텔리전스 조회 실패" })));
  }, [client, service]);
  const tab = useMemo(() => tabs.find((item) => item.label === active) ?? tabs[0], [active, tabs]);
  const result = results[tab.action] ?? null;
  const error = errors[tab.action] ?? "";
  useEffect(() => { writeCache(client, service, { active, fields, results, errors }); }, [active, client, errors, fields, results, service]);
  if (summaryOnly) return <Summary snapshot={snapshot} />;
  function update(name: string, value: string) {
    setFields((current) => ({ ...current, [name]: value,
      ...(name === "symbols" || name === "asset_type" ? { market_preset: "직접 입력" } : {}),
      ...(name === "market_preset" && MARKET_PRESETS[value] ? { symbols: MARKET_PRESETS[value].map((item) => item.symbol).join(",") } : {}),
    }));
    setResults((current) => ({ ...current, [tab.action]: undefined }));
  }
  async function run() {
    setBusy(true); setErrors((current) => ({ ...current, [tab.action]: "" }));
    try {
      let payload: Record<string, unknown> = { ...fields, use_network: true };
      if (tab.action === "market") {
        const universe = fields.market_preset === "직접 입력"
          ? fields.symbols.split(",").map((symbol) => symbol.trim()).filter(Boolean).map((symbol) => ({ symbol, asset_type: fields.asset_type }))
          : (MARKET_PRESETS[fields.market_preset] ?? []);
        if (!universe.length) throw new Error("종목을 한 개 이상 입력하세요.");
        payload = { ...payload, universe };
      }
      const next = await client.runFinancialIntelligence(service, tab.action, payload);
      setResults((current) => ({ ...current, [tab.action]: next }));
    } catch (reason) { setErrors((current) => ({ ...current, [tab.action]: reason instanceof Error ? reason.message : "금융 인텔리전스 실행 실패" })); }
    finally { setBusy(false); }
  }
  const assistantPrompt = `금융 인텔리전스의 '${tab.title}' 기능을 처음 쓰는 사용자에게 입력값, 버튼, 결과 읽는 순서와 데이터 연결 필요 표시가 실제 주문과 어떤 관계인지 설명해줘.`;
  const resultPayload = (result?.result ?? result) as Record<string, any> | null;
  const resultUnavailable = Boolean(resultPayload && (
    ["unavailable", "not_configured", "configuration_required", "no_data", "data_required", "missing_provider", "provider_not_configured", "empty"].includes(String(resultPayload.status))
    || resultPayload.data_sufficient === false
  ));
  const marketPoints = (resultPayload?._chart_points ?? resultPayload?.chart_points ?? resultPayload?.market?._chart_points ?? resultPayload?.market?.chart_points ?? []) as Array<Record<string, any>>;
  return <section className="data-workspace legacy-intelligence-workspace">
    <article className="panel intelligence-header"><h2>NoahAI 금융 인텔리전스</h2><p>종목이나 시장을 선택하면 앱이 공개 시세와 연결된 운영 데이터를 불러옵니다. JSON 파일을 만들거나 붙여 넣을 필요가 없습니다.</p><small>일부 뉴스·공시·기관 데이터는 운영 공급자 연결 전까지 ‘데이터 연결 필요’로 표시되며 임의 값을 만들지 않습니다.</small>{service === "blockchain" && <strong>코인 정보는 내 계좌·선택 코인의 운용 상태를 보는 화면이고, 코인 탐색은 여러 코인을 조건으로 비교해 후보를 찾는 시장 검색 화면입니다.</strong>}</article>
    <nav className="intelligence-tabs" aria-label="금융 인텔리전스 기능">{tabs.map((item) => <button type="button" key={item.label} className={item.label === tab.label ? "active" : ""} onClick={() => setActive(item.label)}>{item.label}{results[item.action] && <i aria-label="조회 결과 보존됨" />}</button>)}</nav>
    <article className="panel intelligence-action-panel"><div className="panel-heading"><div><h2>{tab.title}</h2></div><button className="secondary-button" type="button" onClick={() => onAskAssistant?.(assistantPrompt)}>AI에게 사용법 묻기</button></div><p className="workspace-copy">{tab.description}</p><p className="feature-guide">처음 사용: {tab.guide}</p><span className={`state-pill ${error ? "danger" : resultUnavailable ? "warn" : result ? "ok" : "warn"}`}>{busy ? "수집·계산 중" : error ? "확인 필요" : resultUnavailable ? "데이터 연결·수집 필요" : result ? "완료" : "조회 전"}</span>
      <div className="intelligence-controls">
        {tab.action === "market" && <><select aria-label="시장 프리셋" value={fields.market_preset} onChange={(e) => update("market_preset", e.target.value)}>{[...Object.keys(MARKET_PRESETS), "직접 입력"].map((name) => <option key={name}>{name}</option>)}</select><input aria-label="조회 종목 (수정 시 직접 입력)" value={fields.market_preset === "직접 입력" ? fields.symbols : (MARKET_PRESETS[fields.market_preset] ?? []).map((item) => item.symbol).join(",")} onChange={(e) => update("symbols", e.target.value)} placeholder="예: 삼성전자 005930.KS, Apple AAPL, BTC" /><select aria-label="자산 유형" disabled={fields.market_preset !== "직접 입력"} value={fields.asset_type} onChange={(e) => update("asset_type", e.target.value)}><option value="stock">stock</option><option value="etf">etf</option><option value="index">index</option><option value="fx">fx</option><option value="commodity">commodity</option><option value="crypto">crypto</option></select>{fields.market_preset !== "직접 입력" && <small>프리셋은 종목별 자산 유형을 사용합니다. 종목을 수정하면 직접 입력으로 전환됩니다.</small>}</>}
        {tab.action === "fundamental" && <><select value={fields.provider} onChange={(e) => update("provider", e.target.value)}><option>DART</option><option>SEC</option></select><input value={fields.code} onChange={(e) => update("code", e.target.value)} placeholder="DART 기업코드 또는 SEC CIK" /><input value={fields.year} onChange={(e) => update("year", e.target.value)} aria-label="사업연도" /></>}
        {tab.action === "valuation" && <><label>기준 잉여현금흐름<input value={fields.base_fcf} onChange={(e) => update("base_fcf", e.target.value)} /></label><label>발행주식 수<input value={fields.shares} onChange={(e) => update("shares", e.target.value)} /></label><label>순부채<input value={fields.net_debt} onChange={(e) => update("net_debt", e.target.value)} /></label></>}
        {tab.action === "screener" && <><input value={fields.symbols} onChange={(e) => update("symbols", e.target.value)} aria-label="관심 종목" /><label>최소 가격<input value={fields.min_price} onChange={(e) => update("min_price", e.target.value)} /></label></>}
        {tab.action === "technical" && <input value={fields.symbol} onChange={(e) => update("symbol", e.target.value)} aria-label="종목" />}
        {tab.action === "backtest" && <><label>종목<input value={fields.symbol} onChange={(e) => update("symbol", e.target.value)} /></label><label>빠른 평균<input value={fields.fast} onChange={(e) => update("fast", e.target.value)} /></label><label>느린 평균<input value={fields.slow} onChange={(e) => update("slow", e.target.value)} /></label></>}
        <button className="primary-button" type="button" onClick={() => void run()} disabled={busy}>{busy ? "실행 중…" : tab.button}</button>
      </div>{error && <div className="inline-notice error-text">{error}</div>}<div className="legacy-intelligence-output">{resultPayload ? <ResultView action={tab.action} payload={resultPayload} marketPoints={marketPoints} /> : <div className="legacy-intelligence-placeholder">조회 버튼을 누르면 결과가 여기에 표시됩니다. 다른 탭으로 이동해도 이번 실행 중에는 조회 결과가 유지됩니다.</div>}</div><div className={`legacy-intelligence-result-status ${error ? "error-text" : ""}`}>{busy ? "공개 시세와 연결된 운영 데이터를 조회하고 있습니다." : error || (resultUnavailable ? "분석 결과 없음 · 공급자 연결 상태와 수집 오류를 확인하세요." : result ? "조회가 완료되었습니다. 기준 시각과 출처를 확인하세요." : "조회 전")}</div>
    </article>
  </section>;
}
