// Browser form -> real Python compiler/validator, no provider/account gateway.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const baseURL = process.env.QA_BASE_URL || 'http://127.0.0.1:4198';
process.env.PYTHONUTF8 = '1';
const py = (code, payload) => JSON.parse(execFileSync(process.env.QA_PYTHON || (process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python'), ['-c', code], { input: JSON.stringify(payload), encoding: 'utf8' }));
const analyze = payload => py('import sys,json; from trading.strategy_source_ingestor import StrategySourceIngestor; p=json.load(sys.stdin); print(json.dumps(StrategySourceIngestor().analyze(p["value"],kind="text", supplemental_text=p.get("supplemental_text","")),ensure_ascii=False))', payload);
const validate = payload => py('import sys,json; from web_platform.application_services import ApplicationServices; p=json.load(sys.stdin); print(json.dumps(ApplicationServices.validate_strategy_draft(None,rules=p["rules"]),ensure_ascii=False))', payload);
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
try {
  for (const service of ['crypto', 'stock']) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    await page.exposeFunction('__qaAnalyze', analyze);
    await page.exposeFunction('__qaValidate', payload => { const result = validate(payload); if (!result.ready) console.error(JSON.stringify({issues:result.compiler_issues, details:result.blocking_details, numericValues:payload.rules.executable_entry})); return result; });
    await page.goto(`${baseURL}/qa/strategy-feedback.html?service=${service}`);
    await page.getByRole('navigation', {name:'전략 스튜디오 작업 선택'}).getByRole('button', {name:/내 전략 만들기/}).click();
    const original = '15분봉 RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%, 자산 5%. 횡보장에서 사용.';
    await page.locator('.source-editor').fill(original);
    await page.getByRole('button', {name:'AI 분석 및 전략 초안 만들기', exact:true}).click();
    await page.waitForFunction(() => document.querySelector('.legacy-result-save-row button')?.disabled === false);
    await page.locator('.strategy-validation-settings select').selectOption('15m');
    // No checkbox or risk edit: save must keep the compiler hash valid.
    await page.locator('.legacy-result-save-row button').click();
    await page.waitForFunction(() => !!window.__qaSubmitted, null, {timeout:5000}).catch(async e => { console.error((await page.locator('body').innerText()).split('\n').filter(x=>/실패|누락|확인하세요|저장 전에|변경|계약/.test(x)).join('\n')); throw e; });
    const submitted = await page.evaluate(() => window.__qaSubmitted);
    assert.equal(validate({rules:submitted.rules}).ready, true);
    assert.deepEqual(submitted.rules.risk_model, analyze({value:original}).rules.risk_model);
    assert.deepEqual(submitted.rules.executable_entry, analyze({value:original}).rules.executable_entry);
    assert.deepEqual(errors, []);
    console.log('PASS real compiler -> browser unchanged save -> real validator', service);
    await page.close();

    const repair = await browser.newPage({viewport:{width:900,height:1000}});
    await repair.exposeFunction('__qaValidate', payload => { const result=validate(payload); if(!result.ready) console.error(result); return result; });
    repair.on('dialog', dialog => dialog.accept());
    await repair.goto(`${baseURL}/qa/strategy-feedback.html?service=${service}&repair=1`);
    await repair.getByRole('button',{name:'기본 AI 진입 방식으로 새 버전 만들기',exact:true}).click();
    await repair.getByRole('button',{name:'변경값 재검증 후 다음 버전 저장',exact:true}).click();
    await repair.waitForFunction(() => !!window.__qaSubmitted,null,{timeout:5000}).catch(async e=> {console.error((await repair.locator('body').innerText()).slice(-6500));throw e;});
    const fixed=await repair.evaluate(()=>({submitted:window.__qaSubmitted,original:JSON.parse(window.__qaOriginalVersions),commands:window.__qaRuntimeCommands}));
    assert.equal(fixed.submitted.strategy_key,'paused');
    assert.equal(fixed.submitted.rules.entry_contract.confirmed_by_user,true);
    assert.equal(validate({rules:fixed.submitted.rules}).source_strategy_logic_executed,false);
    assert.deepEqual(fixed.original[0].rules.executable_entry,{all:[],any:[]});
    assert.equal(fixed.commands,undefined);
    console.log('PASS explicit old-version repair -> real validator, no runtime commands',service);
    await repair.close();

    const draft=await browser.newPage({viewport:{width:900,height:1000}});
    await draft.exposeFunction('__qaValidate',validate);
    await draft.goto(`${baseURL}/qa/strategy-feedback.html?service=${service}&repair=1`);
    await draft.getByRole('button',{name:'원문·규칙 보완하기',exact:true}).click();
    await draft.waitForFunction(() => document.activeElement?.classList.contains('strategy-repair-focus'));
    assert.match(await draft.locator('[data-testid="strategy-compatibility-help"]').innerText(), /반복 생성해도 해결되지 않습니다/);
    assert.equal(await draft.locator('.source-editor').inputValue(), '기존 문서의 유동성 반전 진입');
    await draft.getByRole('button',{name:'미완성 초안 보관 · 실행 안 함',exact:true}).click();
    await draft.waitForFunction(()=>!!window.__qaSubmitted);
    const incomplete=await draft.evaluate(()=>({rules:window.__qaSubmitted.rules,commands:window.__qaRuntimeCommands}));
    assert.equal(validate({rules:incomplete.rules}).ready,false);
    assert.equal(incomplete.commands,undefined);
    console.log('PASS incomplete draft saved without execution approval',service);
    await draft.close();

    const interview=await browser.newPage({viewport:{width:1100,height:1000}});
    await interview.exposeFunction('__qaAnalyze',analyze);
    await interview.exposeFunction('__qaValidate',validate);
    await interview.goto(`${baseURL}/qa/strategy-feedback.html?service=${service}&repair=1&named_repair=1`);
    await interview.getByLabel('보완할 기존 버전 선택').selectOption(`${service==='stock'?'unified':'binance'}:paused`);
    const source=await interview.locator('.source-editor').inputValue();
    await interview.getByRole('button',{name:'분석하고 보완 질문 받기',exact:true}).click();
    const answer=interview.locator('.strategy-clarification-panel li').filter({hasText:'confirmed_setup = ...'}).getByRole('textbox');
    await answer.fill('signal == LONG AND rsi <= 35');
    await interview.getByRole('button',{name:'답변 확정 후 다시 분석',exact:true}).click();
    await interview.waitForFunction(()=>window.__qaSourcePayload?.supplemental_text==='confirmed_setup = signal == LONG AND rsi <= 35');
    await interview.waitForFunction(()=>document.querySelector('.legacy-result-save-row button')?.disabled===false);
    await interview.locator('.legacy-result-save-row button').click();
    await interview.waitForFunction(()=>!!window.__qaSubmitted);
    const repaired=await interview.evaluate(()=>({submitted:window.__qaSubmitted,original:JSON.parse(window.__qaOriginalVersions),commands:window.__qaRuntimeCommands}));
    assert.equal(repaired.submitted.strategy_key,'paused');
    assert.equal(repaired.original[0].rules.source_evidence.text,source);
    assert.equal(validate({rules:repaired.submitted.rules}).ready,true);
    assert.equal(repaired.commands,undefined);
    console.log('PASS existing source -> actual question answer -> recompile -> same strategy new version',service);
    await interview.close();
  }
  for (const venue of ['binance','okx','bybit','bitget','upbit','bithumb','coinone','kis','kiwoom','shinhan','mirae']) {
    const recovery=await browser.newPage();
    await recovery.goto(`${baseURL}/qa/strategy-feedback.html?view=recovery&venue=${venue}`);
    await recovery.getByRole('button',{name:'기관 연결 확인 · 거래 시작 안 함',exact:true}).click();
    await recovery.getByText('기관 연결을 확인했습니다.',{exact:false}).waitFor();
    assert.deepEqual(await recovery.evaluate(()=>window.__qaAccountQueries),[venue]);
    await recovery.getByRole('button',{name:'거래 기록 점검·복구 실행 / 이어서 실행',exact:true}).click();
    await recovery.getByText('대상 기록 점검 완료 · 운용 조건은 별도 확인',{exact:true}).waitFor();
    assert.equal(await recovery.evaluate(()=>window.__qaRecoveryStart),venue);
    assert.equal(await recovery.evaluate(()=>window.__qaRuntimeCommands),undefined);
    console.log('PASS recovery UI connection -> maintenance, no trading command',venue);
    await recovery.close();
  }
  for (const status of ['credential_required','invalid_api_keys','timeout','error','unknown']) {
    const recovery=await browser.newPage();
    await recovery.goto(`${baseURL}/qa/strategy-feedback.html?view=recovery&venue=binance&account_status=${status}`);
    await recovery.getByRole('button',{name:'기관 연결 확인 · 거래 시작 안 함',exact:true}).click();
    await recovery.getByText('거래는 시작하지 않았습니다.',{exact:false}).waitFor();
    assert.equal(await recovery.getByText('기관 연결을 확인했습니다.',{exact:false}).count(),0);
    assert.equal(await recovery.evaluate(()=>window.__qaRecoveryStart),undefined);
    assert.equal(await recovery.evaluate(()=>window.__qaRuntimeCommands),undefined);
    console.log('PASS failed connection not certified, no automatic recovery/start',status);
    await recovery.close();
  }
} finally { await browser.close(); }
