import { useEffect, useMemo, useState } from "react";

import { createGatewayClient } from "./api";
import { MarketChart } from "./components/MarketChart";
import type { CandleSnapshot, FeatureInventory, PlatformContract, RuntimeSnapshot } from "./types";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

export default function App() {
  const client = useMemo(() => createGatewayClient(), []);
  const [platform, setPlatform] = useState<PlatformContract | null>(null);
  const [features, setFeatures] = useState<FeatureInventory | null>(null);
  const [runtime, setRuntime] = useState<RuntimeSnapshot | null>(null);
  const [candles, setCandles] = useState<CandleSnapshot | null>(null);
  const [interval, setInterval] = useState("15m");
  const [activeService, setActiveService] = useState("blockchain");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    Promise.all([
      client.platform(),
      client.features(),
      client.runtime(),
      client.candles("BTCUSDT", interval),
    ])
      .then(([nextPlatform, nextFeatures, nextRuntime, nextCandles]) => {
        if (!alive) return;
        setPlatform(nextPlatform);
        setFeatures(nextFeatures);
        setRuntime(nextRuntime);
        setCandles(nextCandles);
        setError("");
      })
      .catch((reason: unknown) => {
        if (alive) setError(reason instanceof Error ? reason.message : "Web UI 초기화에 실패했습니다.");
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [client, interval]);

  const selected = features?.services.find((service) => service.id === activeService);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">N</div>
          <div>
            <strong>NoahAI</strong>
            <span>금융 운영 OS</span>
          </div>
        </div>
        <div className="release-strip">
          <span className="status-dot" />
          <span>{platform?.release_label ?? "v3.9.1.0 Web UI Major Transition"}</span>
          <b>Stage 0 · 읽기 전용</b>
        </div>
        <button className="ghost-button" type="button" disabled>설정은 기존 UI에서 관리</button>
      </header>

      <nav className="service-nav" aria-label="주요 서비스">
        {features?.services.map((service) => (
          <button
            className={service.id === activeService ? "active" : ""}
            key={service.id}
            onClick={() => setActiveService(service.id)}
            type="button"
          >
            {service.label}
          </button>
        ))}
      </nav>

      <main>
        {error && <div className="error-banner"><b>Gateway 연결 확인</b><span>{error}</span></div>}
        <section className="hero-grid">
          <article className="panel chart-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">PUBLIC MARKET · BINANCE SPOT</span>
                <h1>BTC / USDT</h1>
              </div>
              <div className="intervals">
                {INTERVALS.map((value) => (
                  <button
                    className={interval === value ? "active" : ""}
                    key={value}
                    onClick={() => setInterval(value)}
                    type="button"
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            {loading && !candles ? <div className="chart-placeholder">시장 데이터를 불러오는 중입니다.</div> : <MarketChart snapshot={candles} />}
          </article>

          <aside className="panel runtime-panel">
            <span className="eyebrow">LEGACY ENGINE BRIDGE</span>
            <h2>실행 상태</h2>
            <div className={`runtime-state ${runtime?.status ?? "detached"}`}>
              <span>{runtime?.status === "ready" ? "연결됨" : "분리 상태"}</span>
              <strong>{runtime?.selected_source?.toUpperCase() ?? "ENGINE 대기"}</strong>
            </div>
            <dl>
              <div><dt>활성 범위</dt><dd>{runtime?.enabled_sources.length ?? 0}곳</dd></div>
              <div><dt>실행 범위</dt><dd>{runtime?.running_sources.length ?? 0}곳</dd></div>
              <div><dt>PAPER</dt><dd>{runtime?.paper_trading == null ? "—" : runtime.paper_trading ? "ON" : "OFF"}</dd></div>
              <div><dt>LIVE</dt><dd>{runtime?.live_trading == null ? "—" : runtime.live_trading ? "ON" : "OFF"}</dd></div>
            </dl>
            <p>{runtime?.reason ?? "읽기 전용 병행 셸은 기존 거래 엔진을 변경하지 않습니다."}</p>
          </aside>
        </section>

        <section className="workspace-grid">
          <article className="panel feature-panel">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">FEATURE PARITY INVENTORY</span>
                <h2>{selected?.label ?? "기능 목록"}</h2>
              </div>
              <span className="count-badge">{selected?.features.length ?? 0}개 기능</span>
            </div>
            <div className="feature-list">
              {selected?.features.map((feature) => (
                <div className="feature-item" key={feature.id}>
                  <div><strong>{feature.label}</strong><span>{feature.route}</span></div>
                  <em>{feature.migration.replaceAll("_", " ")}</em>
                </div>
              ))}
            </div>
          </article>

          <article className="panel safety-panel">
            <span className="eyebrow">SAFETY GATE</span>
            <h2>현재 허용 범위</h2>
            <ul>
              <li className="allowed">시장 차트·기능 목록·런타임 snapshot 조회</li>
              <li className="allowed">버전 계약·서비스 범위 확인</li>
              <li className="blocked">설정 저장·AI 전략 적용·주문 명령 차단</li>
              <li className="blocked">실거래 전환·API 자격증명 접근 차단</li>
            </ul>
            <footer>명령 API는 동등성·감사·복구 검증 후 단계별로만 열립니다.</footer>
          </article>
        </section>
      </main>
    </div>
  );
}
