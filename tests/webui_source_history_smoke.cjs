// Real built UI + real Python ledger-query output, isolated from live accounts.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || '/tmp/noah-replay-qa.HKjloc/node_modules/playwright');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const fixtures = JSON.parse(execFileSync(path.join(root, '.venv/bin/python'), ['tests/test_source_trade_history.py'], {cwd: root, env: {...process.env, PYTHONPATH: root}, encoding: 'utf8'}));
const venues = Object.keys(fixtures), stock = ['kiwoom', 'shinhan', 'mirae', 'kis'];
const inventory = JSON.parse(fs.readFileSync(path.join(root, 'config/web_ui_feature_inventory.json')));
const reports = path.join(root, 'reports/source-history-20260917');
fs.mkdirSync(reports, { recursive: true });
(async () => {
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  const errors = [], writes = [], checks = [];
  let modes = Object.fromEntries(venues.map(v => [v, 'live'])), state = 'ready';
  page.on('pageerror', e => errors.push(e.message));
  await page.addInitScript(() => { window.noahAI = { bootstrap: () => ({ gatewayUrl: location.origin, gatewayToken: 'isolated-history-qa', desktop: false }) }; });
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url()), endpoint = url.pathname;
    if (route.request().method() !== 'GET') writes.push(endpoint);
    let data = {};
    if (endpoint.endsWith('/platform')) data = {release_version:'3.9.1.38', release_label:'v3.9.1.38 격리 LIVE 이력 검증 · 가상 원장'};
    else if (endpoint.endsWith('/session')) data = {authenticated:true, account:'ISOLATED-QA', user:{id:'ISOLATED-QA', user_grade:'premium'}};
    else if (endpoint.endsWith('/features')) data = inventory;
    else if (endpoint.endsWith('/runtime/snapshot')) data = {
      enabled_sources:venues, running_sources:[], selected_sources:{blockchain:'binance',stock:'kiwoom'},
      credential_status:Object.fromEntries(venues.map(v => [v,true])), execution_modes:modes,
      paper_trading:true, live_trading:false, // deliberately conflicting global fallback
    };
    else if (endpoint.endsWith('/settings')) data = {fields:[],revision:'qa'};
    else if (endpoint.includes('/workspaces/')) {
      const source = url.searchParams.get('source') || 'binance';
      if (state === 'http-error') return route.fulfill({status:503, contentType:'application/json',body:JSON.stringify({detail:'isolated failure'})});
      let history = fixtures[source];
      if (state === 'empty') history = {...history,records:[]};
      if (state === 'unavailable') history = {...history,status:'unavailable',records:[],error:'history_read_failed'};
      if (state === 'wrong-source') history = {...history,source:'wrong-source'};
      if (state === 'precision') history = {...history, records:[{...history.records[0],symbol:'TINYUSDT',currency:'USDT',entry_price:0.00000000012,exit_price:0.00000000015,net_pnl:-0.00000000012,evidence:'confirmed'}]};
      data = {source, live_history:history, trading:{recent_trades:[]}, statistics:[],
        paper_positions:[], paper_positions_status:modes[source]==='paper'?'success':'not_paper',
        paper_trades:[{symbol:`${source.toUpperCase()}_PAPER`,exchange:source,closed_at:'2026-09-17 11:00',net_pnl:5,quote_currency:stock.includes(source)?'KRW':'USDT',calculation_status:'valid'}]};
    } else if (endpoint.endsWith('/logs')) data = {lines:[],entries:[],sources:[],categories:[],levels:[]};
    else if (endpoint.includes('audit')) data = {records:[]};
    else if (endpoint.endsWith('/runtime/account-snapshot')) data = {sources:{}};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  const panel = page.locator('.source-trade-history');
  async function waitText(text) {
    await page.waitForFunction(text => document.querySelector('.source-trade-history')?.textContent.includes(text), text, {timeout:20000});
  }
  try {
    await page.goto(process.env.NOAHAI_QA_URL || 'http://127.0.0.1:4176');
    for (const venue of venues) {
      await page.getByRole('button',{name:stock.includes(venue)?'주식/증권':'블록체인',exact:true}).click();
      await page.locator('.source-tab-strip').getByRole('button',{name:venue.toUpperCase(),exact:true}).click();
      await waitText('현재 LIVE 거래내역');
      assert.equal(await panel.getByRole('button',{name:'펼치기',exact:true}).getAttribute('aria-expanded'),'false');
      assert.equal(await panel.locator('.source-live-history-row').count(),0);
      assert.equal(await page.locator('.exchange-positions h3').innerText(),stock.includes(venue)?'보유자산':['upbit','bithumb','coinone'].includes(venue)?'계좌 보유자산':'포지션');
      assert.equal(await page.locator('.exchange-statistics h3').first().innerText(),'실거래 통계 · 오늘');
      await panel.getByRole('button',{name:'펼치기',exact:true}).click();
      await waitText('체결 대조 완료');
      assert.match(await panel.innerText(), /현재 LIVE 거래내역/);
      assert.ok((await panel.innerText()).includes(`${venue.toUpperCase()} · 저장된 LIVE`));
      assert.ok(!(await panel.innerText()).includes('PAPER_MUST_NOT_LEAK'));
      assert.equal(await panel.locator('.source-live-history-row').count(), fixtures[venue].records.length);
      if (stock.includes(venue)) { assert.match(await panel.innerText(), /005930/); assert.match(await panel.innerText(), /069500/); assert.match(await panel.innerText(), /1,200 KRW/); }
      await panel.locator('summary').first().click();
      assert.match(await panel.innerText(), /trend_follow.*v-test/);
      await panel.getByRole('button',{name:'PAPER 검증 이력',exact:true}).click();
      await panel.getByRole('button',{name:'펼치기',exact:true}).click();
      assert.ok((await panel.innerText()).includes(`${venue.toUpperCase()}_PAPER`));
      assert.equal(await panel.locator('.source-live-history-row').count(),0);
      await panel.getByRole('button',{name:'LIVE 거래내역',exact:true}).click();
      // Runtime poll, without reload: override user's historical tab when mode changes.
      modes[venue]='paper'; await waitText('현재 PAPER 거래내역');
      assert.equal(await panel.getByRole('button',{name:'펼치기',exact:true}).getAttribute('aria-expanded'),'false');
      await page.waitForFunction(()=>document.querySelector('.exchange-positions h3')?.textContent==='가상 포지션',null,{timeout:20000});
      assert.equal(await page.locator('.exchange-statistics h3').first().innerText(),'가상 거래 통계 · 전체');
      await panel.getByRole('button',{name:'펼치기',exact:true}).click();
      assert.ok((await panel.innerText()).includes(`${venue.toUpperCase()}_PAPER`));
      modes[venue]='live'; await waitText('현재 LIVE 거래내역');
      assert.equal(await panel.getByRole('button',{name:'LIVE 거래내역',exact:true}).getAttribute('aria-pressed'),'true');
      assert.equal(await panel.getByRole('button',{name:'펼치기',exact:true}).getAttribute('aria-expanded'),'false');
      if (['binance','kiwoom'].includes(venue)) {
        await panel.screenshot({path:path.join(reports,`${venue}-collapsed.png`)});
        await page.screenshot({path:path.join(reports,`${venue}-collapsed-screen.png`)});
        await panel.getByRole('button',{name:'펼치기',exact:true}).click();
        await panel.screenshot({path:path.join(reports,`${venue}-live.png`)});
        await page.screenshot({path:path.join(reports,`${venue}-screen.png`)});
      }
      checks.push(`${venue}: source isolation, LIVE/PAPER switch, collapsed defaults, position/statistics labels, history preservation, strategy evidence`);
      console.log(`PASS ${venue}`);
    }
    modes.kis='learning'; await waitText('LEARNING은 신규 주문');
    modes.kis='live'; await waitText('현재 LIVE 거래내역');
    await panel.getByRole('button',{name:'펼치기',exact:true}).click();
    state='empty'; await waitText('저장된 LIVE 종료 기록이 없습니다');
    for (const failure of ['unavailable','wrong-source','http-error']) {
      state=failure; await waitText('LIVE 거래내역을 확인하지 못했습니다');
      assert.equal(await panel.locator('.source-live-history-row').count(),0);
      assert.ok(!(await panel.innerText()).includes('종료 기록이 없습니다'));
      if (failure==='http-error') await panel.screenshot({path:path.join(reports,'read-failure.png')});
      state='ready'; await waitText('체결 대조 완료');
    }
    await page.setViewportSize({width:1080,height:900});
    await panel.scrollIntoViewIfNeeded();
    assert.ok(await panel.evaluate(e => e.scrollWidth <= e.clientWidth+1));
    await panel.screenshot({path:path.join(reports,'stock-1080.png')});
    state='precision';
    await page.getByRole('button',{name:'블록체인',exact:true}).click();
    await page.locator('.source-tab-strip').getByRole('button',{name:'BINANCE',exact:true}).click();
    await panel.getByRole('button',{name:'펼치기',exact:true}).click();
    await waitText('TINYUSDT');
    await panel.locator('summary').first().click();
    assert.match(await panel.innerText(), /-0\.00000000012 USDT/);
    assert.match(await panel.innerText(), /0\.00000000015 USDT/);
    assert.deepEqual(errors,[]);
    // Existing read-only account refresh uses POST; it is not a trade command.
    assert.deepEqual(writes.filter(p=>p !== '/api/v1/runtime/account-snapshot'),[]);
    checks.push('LEARNING, empty, unavailable, wrong-source, HTTP failure/recovery, 1080px, tiny coin prices and negative PnL');
    fs.writeFileSync(path.join(reports,'result.json'), JSON.stringify({synthetic_ledger:true,live_account_test:false,checks,errors,writes},null,2));
    console.log(JSON.stringify({venues:venues.length,checks,errors}));
  } catch (error) {
    console.error('UI STATE', state, await panel.innerText().catch(()=>'panel missing'));
    await page.screenshot({path:path.join(reports,'failure-debug.png')});
    throw error;
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
