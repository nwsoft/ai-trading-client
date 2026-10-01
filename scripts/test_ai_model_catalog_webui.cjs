// Vite fixture server: 127.0.0.1:4187. No user account, API key or trading.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const { execFileSync } = require('node:child_process');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const catalog = JSON.parse(execFileSync(path.join(root, '.venv/bin/python'), ['-c', `
import json
from trading.ai.model_registry import MODEL_REGISTRY, CATALOG_AS_OF, selectable_models
from trading.ai.provider_catalog import PRICE_SNAPSHOT_AS_OF, OFFICIAL_PRICING_URLS, model_catalog_details
print(json.dumps(dict(model_catalogs={p:{c:selectable_models(p,capability=c) for c in ('chat_text','chat_json','transcribe')} for p in MODEL_REGISTRY}, model_catalog_details={p:model_catalog_details(p) for p in MODEL_REGISTRY}, model_catalog_meta=dict(model_as_of=CATALOG_AS_OF,price_as_of=PRICE_SNAPSHOT_AS_OF,pricing_urls=OFFICIAL_PRICING_URLS))))
`], { cwd: root, encoding: 'utf8' }));
const field = (path, value, kind, options = []) => ({ path, value, kind, options, label: path, group: 'QA', section: 'ai_engine', presentation: 'primary', help: 'Isolated test', risk: 'normal', minimum: null, maximum: null });
const snapshot = { ...catalog, schema_version: 'qa', revision: 'qa', account_scope: 'isolated', credential_status: {}, fields: [
  field('ai_model_roles.frequent_cheap.provider', 'openai', 'select', Object.keys(catalog.model_catalogs)),
  field('ai_model_roles.frequent_cheap.model', 'gpt-5.6-luna', 'model_select', catalog.model_catalogs.openai.chat_text),
] };
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome' });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  await page.route('**/*', async route => {
    const url = route.request().url();
    if (!url.startsWith('http://127.0.0.1:4187/')) return route.abort();
    if (url.endsWith('/qa/model-catalog.json')) return route.fulfill({ json: snapshot });
    return route.continue();
  });
  try {
    for (const width of [1080, 1490]) {
      await page.setViewportSize({ width, height: 970 });
      await page.goto('http://127.0.0.1:4187/qa/model-refresh.html');
      await page.getByRole('button', { name: 'AI 엔진/API', exact: true }).click();
      await page.getByText('모델 목록 갱신 · 기존 선택 유지', { exact: true }).waitFor();
      const model = page.locator('[data-setting-path="ai_model_roles.frequent_cheap.model"] select');
      assert.equal(await model.inputValue(), 'gpt-5.6-luna');
      assert.equal(await page.evaluate(() => window.modelQaMutations.length), 0);
      assert(await page.locator('.settings-ai-model-catalog').innerText().then(t => t.includes('입력 $0.1 · 출력 $0.5')));
      await model.selectOption('gpt-6-luna');
      await page.getByRole('button', { name: '▣ 현재 설정 저장', exact: true }).click();
      await page.waitForFunction(() => window.modelQaMutations.length === 1);
      assert.deepEqual(await page.evaluate(() => window.modelQaMutations[0]), { 'ai_model_roles.frequent_cheap.model': 'gpt-6-luna' });
      const card = page.locator('.settings-ai-model-grid article').first();
      await card.scrollIntoViewIfNeeded();
      assert((await card.innerText()).includes('GPT-6 Luna'));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await page.screenshot({ path: `/tmp/noah-model-catalog-${width}.png` });
    }
    assert.deepEqual(errors, []);
    console.log('PASS: actual Python catalog, 1080/1490px render, legacy choice, Luna selection, scoped mock save, no external calls, JS errors 0');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
