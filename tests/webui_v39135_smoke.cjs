// Isolated fixture UI check. No account, exchange or AI provider is contacted.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || "playwright");
const fs = require("node:fs");
const path = require("node:path");
const assert = require("node:assert/strict");
const root = path.resolve(__dirname, "..");
const inventory = JSON.parse(fs.readFileSync(path.join(root, "config/web_ui_feature_inventory.json")));
const runtime = { enabled_sources: ["binance", "bybit", "kis"], running_sources: [],
  selected_sources: { blockchain: "binance", stock: "kis" }, credential_status: {}, paper_trading: true };
const history = { status: "available", error: "", total_count: 57666, confirmed_count: 0, reference_count: 57666,
  first_exit_time: "2025-09-08", last_exit_time: "2026-09-01", detail_limit: 100,
  groups: [{ category: "unreconciled", currency: "USDT", count: 52866, stored_pnl_count: 52866, missing_pnl_count: 0, stored_pnl_sum: 123.45 },
           { category: "imported", currency: "USDT", count: 4800, stored_pnl_count: 4800, missing_pnl_count: 0, stored_pnl_sum: 10 }],
  recent_records: [{ symbol: "HISTORICAL_FIXTURE", exchange: "binance", asset_class: "crypto", currency: "USDT", stored_pnl: 12.5, category: "unreconciled", exit_time: "2026-09-01" }] };
function version(scope, name) {
  return { strategy_key: name, version_id: name + "_v1", version: 1, name, status: "draft",
    missing_conditions: [], guidance: {}, xai: { summary: name }, active: false,
    rules: { target_scope: scope, priority: 7, market_regimes: ["range"], signal_mode: "confirm",
      decision_timeframe: scope === "asset:stock" ? "1d" : "15m", risk_model: { max_leverage: 1 } } };
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  let submittedVersion = null;
  page.on("pageerror", error => { errors.push(error.message); console.error(error.stack); });
  await page.addInitScript(() => {
    window.noahAI = { bootstrap: () => ({ gatewayUrl: window.location.origin, gatewayToken: "isolated-fixture-token", desktop: false }) };
    localStorage.setItem("noahai.strategy-studio-guided.blockchain", "done");
    localStorage.setItem("noahai.strategy-studio-guided.stock", "done");
  });
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const endpoint = url.pathname;
    let payload = {};
    if (endpoint.endsWith("/platform")) payload = { release_version: "3.9.1.35", release_label: "v3.9.1.35 QA FIXTURE" };
    else if (endpoint.endsWith("/session")) payload = { authenticated: true, account: "fixture-only", user: { id: "fixture-only", user_grade: "premium" } };
    else if (endpoint.endsWith("/features")) payload = inventory;
    else if (endpoint.endsWith("/runtime/snapshot")) payload = runtime;
    else if (endpoint.endsWith("/settings")) payload = { fields: [], revision: "fixture" };
    else if (endpoint.endsWith("/strategies") && route.request().method() === "POST") { submittedVersion = route.request().postDataJSON(); payload = { version_id: "fixture_v2", status: "analyzed" }; }
    else if (endpoint.endsWith("/strategies/draft-validation")) payload = { ready: true, rules: route.request().postDataJSON().rules };
    else if (endpoint.endsWith("/strategies")) payload = { strategies: [
      { scope: "binance", strategy_key: "CRYPTO_FIXTURE", versions: [version("asset:crypto", "CRYPTO_FIXTURE")] },
      { scope: "unified", strategy_key: "STOCK_FIXTURE", versions: [version("asset:stock", "STOCK_FIXTURE")] },
    ] };
    else if (endpoint.endsWith("/assistant/ask")) payload = { answer: "보존 확인용 답변 — fixture only" };
    else if (endpoint.includes("/workspaces/")) payload = { trading: {}, logs: [], statistics: [], ai_decisions: [],
      scenario: { available_currencies: ["KRW", "USDT"], policy: {}, scopes: { all: { sample_count: 0, scenarios: [], live_history_evidence: history }, stock: { sample_count: 0, scenarios: [], live_history_evidence: { ...history, total_count: 0, reference_count: 0, groups: [], recent_records: [] } } } } };
    else if (endpoint.endsWith("/logs")) payload = { lines: [], entries: [], sources: [], categories: [], levels: [] };
    else if (endpoint.includes("audit")) payload = { records: [] };
    else if (endpoint.includes("portfolio/analysis")) payload = { live_history_evidence: history, execution_mode: url.searchParams.get("statistics_mode"), allocation_by_currency: {}, performance_by_currency: {}, positions: [], recent_closed_trades: [], account_status: {}, performance_basis: url.searchParams.get("statistics_mode") + " fixture ledger" };
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
  });
  const reports = path.join(root, "reports/v39135-ui");
  fs.mkdirSync(reports, { recursive: true });
  try {
    await page.goto("http://127.0.0.1:4175");
    await page.getByRole("button", { name: "AI 어시스턴트", exact: true }).click();
    await page.locator(".legacy-assistant-workspace input, .assistant-workspace input").count();
    const input = page.locator(".legacy-chat-input input:visible");
    await input.fill("대화 유지 테스트");
    await page.getByRole("button", { name: "전송", exact: true }).click();
    await page.getByText("보존 확인용 답변 — fixture only", { exact: true }).waitFor();
    await page.getByRole("button", { name: "전략 스튜디오", exact: true }).click();
    await page.getByRole("button", { name: "AI 어시스턴트", exact: true }).click();
    await page.getByText("보존 확인용 답변 — fixture only", { exact: true }).waitFor({ state: "visible" });
    await page.screenshot({ path: path.join(reports, "assistant-retained.png") });
    await page.getByRole("button", { name: "전략 스튜디오", exact: true }).click();
    await page.locator(".strategy-card").filter({ hasText: "CRYPTO_FIXTURE" }).waitFor();
    assert.equal(await page.locator(".strategy-card:visible").filter({ hasText: "STOCK_FIXTURE" }).count(), 0);
    const picker = page.locator(".venue-checkbox-picker:visible").first();
    await picker.getByRole("checkbox", { name: /Binance|바이낸스/ }).check();
    await picker.getByRole("checkbox", { name: /Bybit|바이비트/ }).check();
    assert.equal(await picker.locator("input:checked").count(), 2);
    await picker.getByRole("checkbox", { name: /Bybit|바이비트/ }).uncheck();
    await page.locator(".legacy-version-target-row select:visible").selectOption("CRYPTO_FIXTURE");
    await page.getByText("기존 규칙을 새 버전 초안으로 불러왔습니다.", { exact: false }).waitFor();
    await page.screenshot({ path: path.join(reports, "strategy-draft.png") });
    await page.locator("label:visible").filter({ hasText: "우선순위" }).locator("select").selectOption("6");
    await picker.getByRole("checkbox", { name: /Binance|바이낸스/ }).check();
    await picker.getByRole("checkbox", { name: /Bybit|바이비트/ }).check();
    await page.locator(".strategy-version-confirm input").check();
    await page.getByRole("button", { name: "변경값 재검증 후 다음 버전 저장", exact: true }).click();
    await page.getByText("전략 새 버전을 만들었습니다.", { exact: false }).waitFor();
    assert.equal(submittedVersion.scope, "binance");
    assert.equal(submittedVersion.strategy_key, "CRYPTO_FIXTURE");
    assert.equal(submittedVersion.rules.priority, 6);
    assert.equal(submittedVersion.rules.target_scope, "exchange:binance,bybit");
    assert.equal(submittedVersion.rules.source_grounding.confirmed_by_user, true);
    await page.getByRole("button", { name: "주식/증권", exact: true }).click();
    await page.getByRole("button", { name: "전략 스튜디오", exact: true }).click();
    await page.locator(".strategy-card:visible").filter({ hasText: "STOCK_FIXTURE" }).waitFor();
    assert.equal(await page.locator(".strategy-card:visible").filter({ hasText: "CRYPTO_FIXTURE" }).count(), 0);
    await page.screenshot({ path: path.join(reports, "stock-only.png") });
    await page.getByRole("button", { name: "자산 통합", exact: true }).click();
    await page.getByRole("combobox", { name: "성과 원장" }).selectOption("paper");
    await page.getByText("paper fixture ledger").first().waitFor();
    await page.screenshot({ path: path.join(reports, "portfolio-paper.png") });
    for (const tab of ["자산 통합 인사이트", "자산 배분 진단", "리스크 브리핑", "성과·위험 분석"]) {
      await page.getByRole("button", { name: tab, exact: true }).click();
      await page.getByText("저장된 종료 기록 57,666건", { exact: true }).waitFor();
      assert.equal(await page.getByText("성과가 없다는 뜻이지 위험이 없다는 뜻은 아닙니다.", { exact: true }).count(), 0);
    }
    await page.locator(".live-history-evidence summary").click();
    await page.getByText("HISTORICAL_FIXTURE", { exact: true }).waitFor();
    await page.screenshot({ path: path.join(reports, "historical-live-reference.png") });
    await page.getByRole("button", { name: "AI애널리스트", exact: true }).first().click();
    await page.getByRole("button", { name: "시나리오 점검", exact: true }).click();
    await page.getByText("저장된 종료 기록 57,666건", { exact: true }).waitFor();
    assert.equal(await page.getByText("자동매매 실행 → 최소 1건 이상 청산 후 다시 확인하세요.", { exact: true }).count(), 0);
    await page.screenshot({ path: path.join(reports, "scenario-historical-reference.png") });
    await page.getByRole("combobox", { name: "데이터 기준" }).selectOption("stock");
    await page.getByText("저장된 종료 기록 0건", { exact: true }).waitFor();
    assert.deepEqual(errors, []);
    console.log("PASS: assistant retention, scoped catalog, multi-select, version draft, PAPER selector; fixture only");
  } finally {
    await page.screenshot({ path: path.join(reports, "last-screen.png") });
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
