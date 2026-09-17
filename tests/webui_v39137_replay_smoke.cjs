// Isolated UI fixture built from real Python replay output. No live account calls.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const metrics = JSON.parse(execFileSync(process.env.NOAHAI_QA_PYTHON || path.join(root, '.venv/bin/python'), ['tests/test_v39137_replay_visualization.py'], { cwd: root, env: { ...process.env, PYTHONPATH: root }, encoding: 'utf8' }));
const stockMetrics = JSON.parse(execFileSync(process.env.NOAHAI_QA_PYTHON || path.join(root, '.venv/bin/python'), ['tests/test_v39137_replay_visualization.py', '--stock'], { cwd: root, env: { ...process.env, PYTHONPATH: root }, encoding: 'utf8' }));
const inventory = JSON.parse(fs.readFileSync(path.join(root, 'config/web_ui_feature_inventory.json')));
const extraFixtures = [
  { name: 'etf', stock: true, args: ['--etf'] },
  { name: 'low-price', stock: false, args: ['--low-price'] },
  { name: 'zero-trades', stock: false, args: ['--empty'] },
  { name: 'short', stock: false, args: ['--short'] },
].map(item => ({ ...item, metrics: JSON.parse(execFileSync(process.env.NOAHAI_QA_PYTHON || path.join(root, '.venv/bin/python'),
  ['tests/test_v39137_replay_visualization.py', ...item.args], { cwd: root, env: { ...process.env, PYTHONPATH: root }, encoding: 'utf8' })) }));
let matrixFixture = null;
function version(stock = false, legacy = false) {
  const m = structuredClone(matrixFixture?.metrics ?? (stock ? stockMetrics : metrics));
  if (legacy) delete m.replay_visualization;
  return { strategy_key: stock ? 'STOCK_REPLAY' : 'CRYPTO_REPLAY', version_id: 'fixture_v1', version: 1,
    status: 'execution_rejected', active: false, missing_conditions: [], guidance: {}, xai: { summary: '로컬 QA 가상 시세 · 실제 수익 아님' },
    validation_subject: 'custom_entry_logic',
    rules: { target_scope: stock ? 'asset:stock' : 'asset:crypto', priority: 7, market_regimes: ['all'], signal_mode: 'independent', entry_signal: 'LONG', decision_timeframe: stock ? '1d' : '15m' },
    execution_validation: { mode: 'historical_replay', recorded_at: '2026-09-17T03:00:00Z', metrics: m },
    validation_lab: { sample: { total: m.decisions }, performance: { total_return_percent: m.net_pnl_percent, win_rate: m.win_rate, max_drawdown_percent: m.max_drawdown_percent } },
  };
}
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [], writes = [];
  let legacy = false;
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => {
    window.__replayPainted = new Set();
    const fill = CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText = function(text, ...args) {
      if (this.canvas.closest('.strategy-replay-chart')) window.__replayPainted.add(String(text));
      return fill.call(this, text, ...args);
    };
    window.noahAI = { bootstrap: () => ({ gatewayUrl: location.origin, gatewayToken: 'isolated-fixture', desktop: false }) };
    localStorage.setItem('noahai.strategy-studio-guided.blockchain', 'done');
    localStorage.setItem('noahai.strategy-studio-guided.stock', 'done');
  });
  await page.route('**/api/v1/**', async route => {
    const endpoint = new URL(route.request().url()).pathname;
    if (route.request().method() !== 'GET') writes.push(endpoint);
    let payload = {};
    if (endpoint.endsWith('/platform')) payload = { release_version: '3.9.1.38', release_label: 'v3.9.1.38 ISOLATED QA' };
    else if (endpoint.endsWith('/session')) payload = { authenticated: true, account: 'fixture-only', user: { id: 'fixture-only', user_grade: 'premium' } };
    else if (endpoint.endsWith('/features')) payload = inventory;
    else if (endpoint.endsWith('/runtime/snapshot')) payload = { enabled_sources: ['binance', 'kiwoom'], running_sources: [], selected_sources: { blockchain: 'binance', stock: 'kiwoom' }, credential_status: {}, paper_trading: true };
    else if (endpoint.endsWith('/settings')) payload = { fields: [], revision: 'fixture' };
    else if (endpoint.endsWith('/strategies')) payload = { strategies: [
      { scope: 'binance', strategy_key: 'CRYPTO_REPLAY', name: 'CRYPTO_REPLAY', versions: [version(false, legacy)] },
      { scope: 'unified', strategy_key: 'STOCK_REPLAY', name: 'STOCK_REPLAY', versions: [version(true, legacy)] },
    ] };
    else if (endpoint.includes('/workspaces/')) payload = { trading: {}, logs: [], statistics: [], ai_decisions: [] };
    else if (endpoint.endsWith('/logs')) payload = { lines: [], entries: [], sources: [], categories: [], levels: [] };
    else if (endpoint.includes('audit')) payload = { records: [] };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
  });
  const reports = path.join(root, 'reports/v39137-replay');
  fs.mkdirSync(reports, { recursive: true });
  try {
    await page.goto(process.env.NOAHAI_QA_URL || 'http://127.0.0.1:4176');
    await page.getByRole('button', { name: '전략 스튜디오', exact: true }).click();
    async function openChart() {
      await page.locator('.strategy-validation-evidence > summary:visible').first().click();
      await page.locator('.strategy-replay > summary:visible').first().click();
      await page.locator('.strategy-replay canvas:visible').first().waitFor();
      assert.equal(await page.getByRole('alert').filter({ hasText: '차트 표시 실패' }).count(), 0);
      assert.ok(await page.locator('.strategy-replay-chart:visible').evaluate(e => {
        const canvas = e.querySelector('canvas');
        return canvas && canvas.getBoundingClientRect().width > e.clientWidth * .75
          && getComputedStyle(canvas.closest('td')).maxWidth === 'none';
      }), 'global table rules must not clip the price canvas');
    }
    await openChart();
    await page.locator('.replay-table button').first().click();
    assert.match(await page.locator('.replay-selection:visible').innerText(), /#1.*LONG 진입/);
    await page.getByRole('button', { name: '다음 거래', exact: true }).click();
    assert.match(await page.locator('.replay-table tbody').innerText(), /#21 보기/);
    await page.getByRole('button', { name: '전체 구간', exact: true }).click();
    await page.locator('.strategy-replay-chart').screenshot({ path: path.join(reports, 'crypto.png') });
    await page.locator('.replay-table-scroll').screenshot({ path: path.join(reports, 'trades.png') });
    await page.setViewportSize({ width: 1080, height: 900 });
    assert.ok(await page.locator('.strategy-replay-chart').evaluate(e => e.clientWidth > 200));
    await page.locator('.strategy-replay-chart').screenshot({ path: path.join(reports, 'desktop-1080.png') });
    await page.getByRole('button', { name: '주식/증권', exact: true }).click();
    await page.getByRole('button', { name: '전략 스튜디오', exact: true }).click();
    await openChart();
    assert.match(await page.locator('.strategy-replay:visible').innerText(), /KIWOOM.*005930.*1d/);
    assert.match(await page.locator('.replay-table caption:visible').innerText(), /KRW/);
    await page.locator('.strategy-replay-chart:visible').screenshot({ path: path.join(reports, 'stock.png') });
    for (const fixture of extraFixtures) {
      matrixFixture = fixture;
      await page.reload();
      await page.getByRole('button', { name: fixture.stock ? '주식/증권' : '블록체인', exact: true }).click();
      await page.getByRole('button', { name: '전략 스튜디오', exact: true }).click();
      await openChart();
      const rounded = Number(fixture.metrics.net_pnl_percent.toFixed(4));
      const expectedPercent = `${rounded > 0 ? '+' : ''}${rounded.toFixed(4)}%`;
      await page.waitForFunction(text => window.__replayPainted.has(text), expectedPercent);
      assert.equal((await page.evaluate(() => [...window.__replayPainted].filter(t => /^#\d+ /.test(t)))).length, 0);
      if (fixture.name === 'zero-trades') {
        assert.match(await page.locator('.replay-selection:visible').innerText(), /완료된 거래가 없습니다/);
        assert.equal(await page.locator('.replay-table:visible tbody tr').count(), 0);
      } else {
        await page.locator('.replay-table:visible button').first().click();
        await page.waitForFunction(() => [...window.__replayPainted].filter(t => /^#1 /.test(t)).length === 2);
        await page.locator('.replay-raw-values:visible > summary').click();
        assert.match(await page.locator('.replay-raw-values:visible').innerText(), new RegExp(String(fixture.metrics.trades[0].entry_price).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
      }
      if (fixture.name === 'low-price') assert.notEqual(await page.locator('.replay-table:visible span[title]').first().innerText(), '0');
      if (fixture.name === 'short') assert.match(await page.locator('.replay-selection:visible').innerText(), /SELL · SHORT 진입.*BUY · SHORT 청산/);
      if (fixture.name === 'etf') assert.match(await page.locator('.strategy-replay:visible').innerText(), /069500.*1d/);
      await page.locator('.strategy-replay-chart:visible').screenshot({ path: path.join(reports, `${fixture.name}.png`) });
    }
    matrixFixture = null;
    legacy = true;
    await page.reload();
    await page.getByRole('button', { name: '전략 스튜디오', exact: true }).click();
    await page.locator('.strategy-validation-evidence > summary:visible').first().click();
    await page.locator('.strategy-replay > summary:visible').first().click();
    await page.getByText('이 결과에는 연결 가능한 원본 캔들', { exact: false }).waitFor();
    assert.equal(await page.locator('.strategy-replay canvas').count(), 0);
    assert.deepEqual(writes.filter(url => /strategies|runtime/.test(url)), []);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ status: 'PASS', engine_trades: metrics.decisions, browser_errors: errors.length,
      checks: ['crypto render', 'trade selection', 'pagination', '1080px desktop', 'stock KRW render', 'ETF', 'low-price coin', 'zero trades', 'SHORT', 'canvas percentage labels', 'selected names only', 'raw price details', 'legacy unavailable', 'no strategy/runtime writes'], reports }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
