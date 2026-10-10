// Actual React + actual local compiler/validator. Account APIs remain synthetic.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.QA_BASE_URL || 'http://127.0.0.1:4198';
process.env.PYTHONUTF8 = '1';
const py=(code,payload)=>JSON.parse(execFileSync(process.env.QA_PYTHON || (process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'),['-c',code],{input:JSON.stringify(payload),encoding:'utf8'}));
const analyze=p=>py('import sys,json; from trading.strategy_source_ingestor import StrategySourceIngestor; p=json.load(sys.stdin); print(json.dumps(StrategySourceIngestor().analyze(p["value"],kind="text"),ensure_ascii=False))',p);
const validate=p=>py('import sys,json; from web_platform.application_services import ApplicationServices; p=json.load(sys.stdin); print(json.dumps(ApplicationServices.validate_strategy_draft(None,rules=p["rules"]),ensure_ascii=False))',p);
const profiles=['beginner','standard','advanced','lab','research'];
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
  for(const service of ['crypto','stock']) for(const [index,profile] of profiles.entries()) {
    const page=await browser.newPage({viewport:{width:index%2?900:1440,height:1100}});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.exposeFunction('__qaAnalyze',analyze);
    await page.exposeFunction('__qaValidate',validate);
    await page.goto(`${base}/qa/strategy-feedback.html?service=${service}&profile=${profile}&replay_state=execution_rejected`);
    await page.waitForFunction(level=>document.querySelector('.legacy-xai-title-group select')?.value.startsWith(`Level ${level}`),index+1);
    await page.getByRole('navigation', {name:'전략 스튜디오 작업 선택'}).getByRole('button', {name:/내 전략 만들기/}).click();
    const options=await page.locator('.legacy-xai-title-group select option').evaluateAll(xs=>xs.map(x=>({value:x.value,disabled:x.disabled})));
    assert.equal(options.length,5);
    assert.deepEqual(options.map(x=>x.disabled),profiles.map((_,i)=>i>index));
    if(index===4) {
      await page.getByRole('navigation', {name:'전략 스튜디오 작업 선택'}).getByRole('button', {name:/전략 사용하기/}).click();
      await page.locator('.version-row').first().locator('.strategy-version-detail > summary').click();
      await page.locator('.version-row').first().locator('.strategy-validation-evidence > summary').click();
      assert.match(await page.getByTestId('research-evidence').innerText(),/누락 비용은 0으로 추정하지 않습니다/);
    }
    await page.getByRole('navigation', {name:'전략 스튜디오 작업 선택'}).getByRole('button', {name:/내 전략 만들기/}).click();
    const original='15분봉 RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.';
    await page.locator('.source-editor').fill(original);
    await page.getByRole('button',{name:'AI 분석 및 전략 초안 만들기',exact:true}).click();
    await page.waitForFunction(()=>document.querySelector('.legacy-result-save-row button')?.disabled===false);
    await page.locator('.strategy-validation-settings select').selectOption('15m');
    await page.locator('.legacy-result-save-row button').click();
    await page.waitForFunction(()=>!!window.__qaSubmitted);
    const saved=await page.evaluate(()=>window.__qaSubmitted);
    assert.equal(validate(saved).ready,true);
    assert.deepEqual(saved.rules.executable_entry,analyze({value:original}).rules.executable_entry);
    assert.deepEqual(saved.rules.risk_model,analyze({value:original}).rules.risk_model);
    const range=page.getByTestId('replay-options'); await range.locator('summary').click();
    await range.getByLabel('시작 UTC',{exact:true}).fill('2026-08-01T00:00');
    await range.getByLabel('종료 UTC · 제외',{exact:true}).fill('2026-08-03T00:00');
    await range.getByLabel('최대 보유 봉 수 · 검사 가정',{exact:true}).fill('24');
    await range.getByLabel('검사 종목',{exact:true}).fill(service==='stock'?'000660':'ETHUSDT');
    page.once('dialog',d=>d.accept());
    // List sorting must not change the identity of the version being tested.
    await page.locator('.strategy-card').filter({has:page.locator('header small',{hasText:/^paused$/})}).getByRole('button',{name:'과거 시세 백테스트 · 선택',exact:true}).click();
    await page.waitForFunction(()=>window.__qaReplayRequests?.length===1);
    const payload=await page.evaluate(()=>window.__qaReplayRequests[0]);
    assert.equal(payload.range_start_ms,Date.parse('2026-08-01T00:00Z'));
    assert.equal(payload.range_end_ms,Date.parse('2026-08-03T00:00Z'));
    assert.equal(payload.holding_bars,24);
    assert.equal(payload.symbol,service==='stock'?'000660':'ETHUSDT');
    assert.equal(await page.evaluate(()=>window.__qaRuntimeCommands),undefined);
    assert.deepEqual(errors,[]);
    console.log('PASS level',index+1,service,'real compiler save, date inputs, no runtime order');
    await page.close();
  }
} finally {await browser.close();}
