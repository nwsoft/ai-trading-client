// Isolated UI + actual local compiler/help; no exchange, Provider or order calls.
const { chromium } = require('/tmp/noah-replay-qa.HKjloc/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:4199';
const output = path.join(root, 'reports/strategy-beginner-20260918');
const inventory = JSON.parse(fs.readFileSync(path.join(root, 'config/web_ui_feature_inventory.json')));
const python = path.join(root, '.venv/bin/python');
const compile = body => JSON.parse(execFileSync(python, ['-c',
  'import sys,json; from trading.strategy_source_ingestor import StrategySourceIngestor; b=json.load(sys.stdin); print(json.dumps(StrategySourceIngestor().analyze(b["value"], "text", supplemental_text=b.get("supplemental_text", ""), authoring_mode=b.get("authoring_mode", "source_faithful")), ensure_ascii=False))'],
  { cwd: root, input: JSON.stringify(body), encoding: 'utf8' }));
const explain = prompt => execFileSync(python, ['-c',
  'import sys; from config.ai_custom_knowledge import build_ai_custom_knowledge; print(build_ai_custom_knowledge(sys.stdin.read()))'], { cwd: root, input: prompt, encoding: 'utf8' });

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const results = [];
  try {
    for (const service of ['blockchain', 'stock']) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
      const errors = [], mutations = [], requests = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.addInitScript(() => {
        window.noahAI = { bootstrap: () => ({ gatewayUrl: location.origin, gatewayToken: 'isolated-beginner-qa', desktop: false }) };
        for (const s of ['blockchain', 'stock']) localStorage.setItem(`noahai.strategy-studio-guided.${s}`, 'done');
      });
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        const endpoint = url.pathname;
        if (!endpoint.startsWith('/api/')) return route.continue();
        if (route.request().method() !== 'GET') mutations.push(endpoint);
        let payload = {};
        if (endpoint.endsWith('/platform')) payload = { release_version: '3.9.1.39', release_label: '초보자 격리 QA · 실제 계정 아님' };
        else if (endpoint.endsWith('/session')) payload = { authenticated: true, account: 'QA', user: { id: 'QA', user_grade: 'premium' } };
        else if (endpoint.endsWith('/features')) payload = inventory;
        else if (endpoint.endsWith('/runtime/snapshot')) payload = { enabled_sources: ['binance', 'kiwoom'], running_sources: [], selected_sources: { blockchain: 'binance', stock: 'kiwoom' }, credential_status: {}, paper_trading: true };
        else if (endpoint.endsWith('/settings')) payload = { fields: [{ path: 'ai_custom_features.profile', value: 'beginner' }, { path: 'paper_trading', value: true }], revision: 'qa' };
        else if (endpoint.endsWith('/strategies/source-analysis')) payload = compile(route.request().postDataJSON());
        else if (endpoint.endsWith('/strategies')) payload = { strategies: [] };
        else if (endpoint.endsWith('/assistant/status')) payload = { budget: { daily_limit: 30, daily_used: 0 }, data_routing: { public_general_enabled: true, public_general_effective: true } };
        else if (endpoint.endsWith('/assistant/ask')) {
          const body = route.request().postDataJSON(); requests.push(body);
          payload = { answer: body.mode === 'guide' ? explain(body.question) : '격리 테스트 답변: 거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.', provider_called: false };
        }
        else if (endpoint.includes('/workspaces/')) payload = { trading: {}, logs: [], statistics: [], ai_decisions: [] };
        else if (endpoint.endsWith('/logs')) payload = { lines: [], entries: [], sources: [], categories: [], levels: [] };
        else if (endpoint.includes('audit')) payload = { records: [] };
        await route.fulfill({ contentType: 'application/json', body: JSON.stringify(payload) });
      });
      await page.goto(base);
      if (service === 'stock') await page.getByRole('button', { name: '주식/증권', exact: true }).click();
      await page.getByRole('button', { name: '전략 스튜디오', exact: true }).click();
      const studio = page.locator('.legacy-strategy-workspace:visible');
      await studio.locator('.strategy-beginner-help summary').click();
      assert.match(await studio.locator('.strategy-beginner-help').innerText(), /SHORT에서는 SELL 진입/);
      await studio.locator('.strategy-beginner-help summary').click();
      await studio.getByRole('button', { name: /질문으로 함께 완성/ }).click();
      await studio.locator('textarea.source-editor').fill('RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%. 횡보장에서 사용.\n저자는 과거 백테스트 승률 60%를 주장한다.');
      await studio.getByRole('button', { name: '분석하고 보완 질문 받기', exact: true }).click();
      const easy = studio.locator('.strategy-beginner-explanation');
      await easy.waitFor();
      assert.match(await easy.innerText(), /RSI/);
      assert.equal(await studio.locator('.legacy-xai-heading select').inputValue(), 'Level 1 이해·시험');
      await easy.locator('summary').click();
      assert.match(await easy.innerText(), /승률 60%/);
      await easy.screenshot({ path: path.join(output, `${service}-explanation.png`) });
      await studio.getByRole('button', { name: '이 결과 AI에게 묻기', exact: true }).click();
      await page.locator('.strategy-context-notice').waitFor();
      assert.ok(!(await page.locator('.legacy-chat-input input').inputValue()).includes('NOAH_STRATEGY_EXPLANATION'));
      await page.getByRole('button', { name: '전송', exact: true }).click();
      await page.getByText(/현재 초안 쉽게 읽기/).waitFor();
      assert.equal(requests[0].mode, 'guide');
      assert.equal(requests[0].data_scope, 'private');
      assert.match(requests[0].question, /RSI 30/);
      const chatBounds = await page.locator('.legacy-chat-panel').boundingBox();
      const inputBounds = await page.locator('.legacy-chat-input').boundingBox();
      assert.ok(inputBounds.y + inputBounds.height <= chatBounds.y + chatBounds.height, 'input must stay inside chat panel');
      assert.ok(inputBounds.y + inputBounds.height < 975, 'input must not be obscured by app footer');
      await page.locator('.assistant-main-grid').screenshot({ path: path.join(output, `${service}-assistant.png`) });
      await page.getByRole('button', { name: '심층분석', exact: true }).click();
      await page.locator('.assistant-public-route input').click();
      assert.match(await page.locator('.inline-notice.error-text').innerText(), /기본 보호 경로/);
      assert.equal(await page.locator('.assistant-public-route input').isChecked(), false);
      await page.locator('.legacy-chat-input input').fill('거래당 허용 손실을 어떻게 표현하나요?');
      await page.getByRole('button', { name: '전송', exact: true }).click();
      await page.getByText('격리 테스트 답변: 거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.', { exact: true }).waitFor();
      assert.match(requests[1].question, /NOAH_STRATEGY_EXPLANATION_V1/);
      assert.equal(requests[1].data_scope, 'private');
      await page.locator('.assistant-send-to-strategy').last().click();
      await studio.locator('.strategy-assistant-draft').waitFor();
      assert.match(await studio.locator('.strategy-assistant-draft textarea').inputValue(), /격리 테스트/);
      await studio.locator('.strategy-assistant-draft textarea').fill('거래당 계좌 손실 0.5%, 증거금 사용은 최대 10%.');
      await studio.getByRole('button', { name: '사용자 보완 근거로 확정·재분석', exact: true }).click();
      await studio.locator('.strategy-confirmed-supplement').waitFor();
      assert.ok((await studio.locator('textarea.source-editor').inputValue()).includes('승률 60%'));
      assert.ok(mutations.every(p => ['/api/v1/strategies/source-analysis', '/api/v1/assistant/ask'].includes(p)), mutations.join(','));
      assert.deepEqual(errors, []);
      // Verify snapshot removal does not silently resend private draft context.
      await studio.getByRole('button', { name: '이 결과 AI에게 묻기', exact: true }).click();
      await page.getByRole('button', { name: '분석 자료·대화 해제', exact: true }).click();
      assert.equal(await page.locator('.strategy-context-notice').count(), 0);
      await page.locator('.legacy-chat-input input').fill('차트 사용법을 알려줘');
      await page.getByRole('button', { name: '전송', exact: true }).click();
      await page.waitForFunction(() => document.querySelector('.legacy-chat-input input')?.value === '');
      assert.ok(!requests.at(-1).question.includes('NOAH_STRATEGY_EXPLANATION'));
      results.push({ service, errors, analysis_calls: mutations.filter(p => p.endsWith('source-analysis')).length, assistant_calls: requests.length, order_save_approve_calls: 0, real_provider_calls: 0 });
      await page.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
