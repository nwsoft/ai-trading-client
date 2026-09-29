// All gateway requests are local synthetic fixtures. Never connects to an account.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const inventory = JSON.parse(fs.readFileSync(path.join(root, 'config/web_ui_feature_inventory.json')));
(async () => {
  const browser = await chromium.launch({headless: true, channel: process.env.NOAHAI_QA_CHANNEL || 'chrome'});
  const page = await browser.newPage({viewport: {width: 1366, height: 900}});
  const errors=[], requests=[], writes=[];
  let mode='paper', missing=false;
  const now=Date.now()/1000;
  page.on('pageerror', e=>errors.push(e.message));
  await page.addInitScript(() => {
    window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})};
    localStorage.setItem('noahai.strategy-studio-guided.blockchain','done');
  });
 if(process.env.NOAHAI_QA_DIST) await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.startsWith('/api/')) return route.fallback();
  const target=path.join(process.env.NOAHAI_QA_DIST,url.pathname==='/'?'index.html':url.pathname);
  const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.svg':'image/svg+xml'};
  if(fs.existsSync(target)&&fs.statSync(target).isFile()) return route.fulfill({body:fs.readFileSync(target),contentType:types[path.extname(target)]||'application/octet-stream'});
  return route.abort();
 });
  await page.route('**/api/v1/**', async route => {
    const url=new URL(route.request().url()), endpoint=url.pathname;
    requests.push(endpoint);
    if (route.request().method() !== 'GET') writes.push(endpoint);
    let payload={};
    if(endpoint.endsWith('/platform')) payload={release_version:'3.9.1.49',release_label:'v3.9.1.49 ISOLATED QA'};
    else if(endpoint.endsWith('/session')) payload={authenticated:true,account:'v49-fixture',user:{id:'fixture',user_grade:'premium'}};
    else if(endpoint.endsWith('/features')) payload=inventory;
    else if(endpoint.endsWith('/runtime/snapshot')) payload={enabled_sources:['upbit','bithumb','kiwoom'],running_sources:['upbit'],selected_sources:{blockchain:'upbit',stock:'kiwoom'},credential_status:{},paper_trading:mode==='paper',execution_modes:{upbit:mode,bithumb:mode,kiwoom:mode}};
    else if(endpoint.endsWith('/settings')) payload={fields:[],revision:'fixture'};
    else if(endpoint.endsWith('/strategies')) payload={strategies:[]};
    else if(endpoint.includes('/workspaces/')) {
      const source=url.searchParams.get('source') || 'upbit';
      payload={source,trading:{},logs:[],statistics:[],ai_decisions:[],paper_positions:[],
        active_custom_strategies:Array.from({length:30},(_,i)=>({name:`검증 ${i}`,operation_mode:'paper_validation'})),
        operation_summary: missing ? undefined : {source,mode,status:'observed',session:'fixture',
          regime:{observed:'bull',confirmed:'range',observed_at:now},
          candidate:{symbol:'KRW-TEST',signal:'LONG',allowed:true,reason:'custom_entry_passed',strategy_name:'완료 봉 돌파',version_id:'fixture-v1',timeframe:'5m',bar_timestamp:(now-300)*1000,observed_at:now,checks:[{passed:true,reason:'close=101 gt_field 100'}]},
          paper_pool:{scope_eligible:40,selected:30,waiting:10,limit:30,applied_slots:0,waiting_versions:[]}}};
    } else if(endpoint.endsWith('/logs')) payload={lines:[{source:'fixture',message:'QA 상세 로그 — 실제 거래 아님'}]};
    else if(endpoint.includes('audit')) payload={records:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
  });
  try {
    await page.goto(process.env.NOAHAI_QA_URL || 'http://127.0.0.1:4209');
    await page.getByRole('button',{name:'거래 대시보드',exact:true}).click();
    await page.getByRole('button',{name:'UPBIT',exact:true}).click();
    await page.getByRole('button',{name:'운용 요약',exact:true}).waitFor();
    assert.equal(await page.locator('.operation-summary').count(),0);
    await page.getByRole('button',{name:'운용 요약',exact:true}).click();
    await page.getByRole('heading',{name:/UPBIT.*운용 요약/}).waitFor();
    assert.match(await page.locator('.operation-summary').innerText(),/평가 대상 30개 · 대기 10개/);
    assert.match(await page.locator('.paper-pool-status').innerText(),/대기 10개/);
    assert.match(await page.locator('.operation-summary').innerText(),/주문 결과 아님/);
    const logsBefore=requests.filter(x=>x.endsWith('/logs')).length;
    await page.waitForTimeout(6100);
    assert.equal(requests.filter(x=>x.endsWith('/logs')).length,logsBefore,'hidden logs must not poll');
    const reports=fs.mkdtempSync(path.join(os.tmpdir(),'noah-v49-ui-'));
    await page.screenshot({path:path.join(reports,'summary.png')});
    await page.setViewportSize({width:1080,height:850});
    assert.ok(await page.locator('.operation-summary').evaluate(e=>e.scrollWidth<=e.clientWidth+1),'summary must wrap');
    await page.reload();
    await page.getByRole('button',{name:'거래 대시보드',exact:true}).click();
    await page.getByRole('button',{name:'UPBIT',exact:true}).click();
    await page.locator('.operation-summary').waitFor();
    missing=true;
    await page.waitForTimeout(5500);
    assert.match(await page.locator('.operation-summary').innerText(),/근거가 아직 없습니다/);
    mode='live';
    await page.waitForTimeout(3000);
    await page.getByRole('heading',{name:/UPBIT.*LIVE.*운용 요약/}).waitFor();
    assert.doesNotMatch(await page.locator('.operation-summary').innerText(),/fixture-v1/);
    await page.getByRole('button',{name:'상세 로그',exact:true}).click();
    await page.locator('.legacy-log-console').waitFor();
    assert.deepEqual(errors,[]);
    assert.deepEqual(writes,[]);
    console.log(JSON.stringify({result:'PASS',reports,errors,writes,requests:requests.length}));
  } catch (error) { console.error((await page.locator('body').innerText()).slice(0,4000)); throw error; }
  finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});
