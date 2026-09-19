const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');

const base = process.env.QA_BASE || 'http://127.0.0.1:4199';
const out = process.env.AUDIT_DIR;
const inventory = JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));

const candleRows = (symbol, count = 45) => ({
  source: symbol.match(/^\d/) ? 'kiwoom' : 'binance',
  symbol,
  interval: '1d',
  captured_at: '2026-09-19T03:00:00Z',
  candles: Array.from({ length: count }, (_, index) => ({
    source: symbol.match(/^\d/) ? 'kiwoom' : 'binance', market_type: symbol.match(/^\d/) ? 'stock' : 'futures', symbol, interval: '1d',
    open_time: 1_700_000_000_000 + index * 86_400_000, close_time: 1_700_086_399_999 + index * 86_400_000,
    open: 100 + index, high: 103 + index, low: 98 + index, close: 101 + index, volume: 1_000 + index * 25, closed: true, sequence: index,
  })),
});

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.QA_CHROME_EXECUTABLE ? { executablePath: process.env.QA_CHROME_EXECUTABLE } : {}),
  });
  const result = { errors: [], assistantRequests: [], stockHistoryPeak: 0 };
  let stockHistoryActive = 0;
  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
    page.setDefaultTimeout(12_000);
    page.on('pageerror', error => result.errors.push(error.message));
    await page.addInitScript(() => {
      window.noahAI = { bootstrap: () => ({ gatewayUrl: location.origin, gatewayToken: 'isolated-market-trend', desktop: false }) };
    });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== base) return route.abort();
      const endpoint = url.pathname;
      if (!endpoint.startsWith('/api/')) return route.continue();
      let payload = {};
      if (endpoint.endsWith('/platform')) payload = { release_version: '3.9.1.41' };
      else if (endpoint.endsWith('/session')) payload = { authenticated: true, account: 'QA', user: { id: 'QA', user_grade: 'premium' } };
      else if (endpoint.endsWith('/features')) payload = inventory;
      else if (endpoint.endsWith('/runtime/snapshot')) payload = { enabled_sources: ['binance', 'kiwoom'], running_sources: [], selected_sources: { blockchain: 'binance', stock: 'kiwoom' }, credential_status: {}, paper_trading: true };
      else if (endpoint.endsWith('/settings')) payload = { fields: [], revision: 'qa' };
      else if (endpoint.endsWith('/assistant/status')) payload = { budget: { daily_limit: 30, daily_used: 0 }, data_routing: {} };
      else if (endpoint.endsWith('/assistant/ask')) {
        const body = route.request().postDataJSON(); result.assistantRequests.push(body);
        payload = { answer: '격리 XAI 답변 · 지지 근거 / 반대·위험 근거 / 무효화 조건 / 누락 데이터', provider_called: false };
      } else if (endpoint.endsWith('/market/stock-overview')) payload = {
        source: 'naver_finance_public', indices: [{ status: 'ok', symbol: 'KOSPI', name: 'KOSPI', change: 0.7 }, { status: 'ok', symbol: 'KOSDAQ', name: 'KOSDAQ', change: -0.2 }],
        quotes: ['005930', '000660', '035420', '035720', '005380', '373220'].map((symbol, index) => ({ status: 'ok', symbol, name: ['삼성전자', 'SK하이닉스', 'NAVER', '카카오', '현대차', 'LG에너지솔루션'][index], price: 100_000 + index * 5_000, change: 1.2 - index * .35, volume: 100_000 + index * 10_000, traded_at: '2026-09-19T12:00:00+09:00', market_status: 'OPEN', source: 'naver_finance_public' })),
      };
      else if (endpoint.endsWith('/market/sentiment')) payload = { source: 'binance', symbol: 'BTCUSDT', funding_rate: .0001, long_short_ratio: 1.08, captured_at: 1_789_784_400_000 };
      else if (endpoint.endsWith('/market/candles')) {
        const symbol = url.searchParams.get('symbol');
        const stock = url.searchParams.get('market_type') === 'stock';
        if (stock) {
          stockHistoryActive += 1; result.stockHistoryPeak = Math.max(result.stockHistoryPeak, stockHistoryActive);
          await new Promise(resolve => setTimeout(resolve, 25)); stockHistoryActive -= 1;
        }
        payload = candleRows(symbol);
      } else if (endpoint.includes('/workspaces/')) payload = { trading: { closed_count: 2, pnl_by_currency: { USDT: 1.2, KRW: 1200 } }, selected_coins: [{ symbol: 'BTCUSDT' }], statistics: [] };
      else if (endpoint.endsWith('/logs')) payload = { lines: [], entries: [], sources: [], categories: [], levels: [] };
      else if (endpoint.includes('/audit')) payload = { records: [] };
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
    });

    await page.goto(base);
    await page.getByRole('button', { name: '시장 트렌드', exact: true }).click();
    await page.locator('.market-asset-grid article').first().waitFor();
    assert.equal(await page.locator('.market-breadth-donut').count(), 1);
    assert.equal(await page.locator('.market-asset-grid article').count(), 3);
    assert.match(await page.locator('.market-trend-kpis').innerText(), /공포·탐욕 지수가 아니라/);
    await page.getByRole('button', { name: '7일', exact: true }).click();
    await page.locator('.market-asset-grid article').first().getByText('+5.07%', { exact: true }).waitFor();
    await page.screenshot({ path: `${out}/crypto-7d.png`, fullPage: true });
    await page.getByRole('button', { name: '관찰 후보 XAI 비교', exact: true }).click();
    const input = page.locator('.legacy-chat-input input');
    assert.equal((await input.inputValue()).includes('[MARKET_TREND_SNAPSHOT]'), false);
    await page.getByRole('button', { name: '전송', exact: true }).click();
    await page.getByText(/격리 XAI 답변/).waitFor();
    assert.match(result.assistantRequests[0].question, /\[MARKET_TREND_SNAPSHOT\]/);

    await page.getByRole('button', { name: '주식/증권', exact: true }).click();
    await page.getByRole('button', { name: '시장 트렌드', exact: true }).click();
    await page.getByRole('button', { name: '30일', exact: true }).click();
    await page.locator('.market-asset-grid article').first().getByText('+26.09%', { exact: true }).waitFor();
    assert.equal(result.stockHistoryPeak, 1);
    assert.equal(await page.locator('.market-asset-grid article').count(), 6);
    await page.screenshot({ path: `${out}/stock-30d.png`, fullPage: true });
    result.cryptoCards = 3; result.stockCards = 6; result.hiddenEvidence = true;
    assert.deepEqual(result.errors, []);
  } catch (error) {
    result.failure = String(error); process.exitCode = 1;
  } finally {
    fs.writeFileSync(`${out}/results.json`, JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
    await browser.close();
  }
})();
