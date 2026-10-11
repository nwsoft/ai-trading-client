// Render the built React product with intercepted synthetic API responses.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const out=path.join(root,process.env.NOAHAI_TEAYU_UI_OUT||'reports/teayu-20261010-patch/ui');
const venues=['binance','upbit','bithumb','coinone','bybit','okx','bitget'];
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 const errors=[],writes=[],checks=[];let running=true,session=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})});
 function evidence(source){
  const now=Date.now()/1000;
  const wallet=['bybit','bitget','upbit','bithumb'].includes(source)&&!session;
  const code=wallet?'paper_ledger_currency_unverified':session&&source==='bybit'?'paper_session_ready':source==='okx'?'trading_candidate_catalogue_unavailable':source==='binance'?'pre_entry_confidence_low':'hold';
  const label=wallet?'과거 PAPER 결제통화 근거 누락':session&&source==='bybit'?'새 PAPER 평가 준비됨':source==='okx'?'현재 종목 목록 조회 실패':source==='binance'?'진입 신뢰도 기준 미충족':'거래 신호 대기';
  return {source,mode:'paper',status:'observed',
   entry_activity:{status:'no_recent_entry',label:'30분 이상 신규 주문 처리 기록 없음',attention:true,action:'최근 판단 분포와 보류 사유를 확인하세요.',observed_since:now-7200,no_entry_seconds:7200,last_cycle_at:now,returned_cycles:20,recent_reasons:[{code:'hold',label:'거래 신호 대기',count:70},{code:'pre_entry_confidence_low',label:'진입 신뢰도 기준 미충족',count:40}],scope:'current_runtime_session',reason_window:128},
   entry_health:{code,label,blocked:!['hold','paper_session_ready'].includes(code),action:wallet?'기관을 정지하고 운용 요약에서 과거 기록을 보존하는 새 PAPER 평가를 준비하세요.':'공개 시세 연결 또는 실제 진입 기준을 확인하세요.',observed_at:now,since:now-3600,consecutive_count:12},
   candidate:{symbol:'BTCUSDT',allowed:true,signal:'LONG',observed_at:now},
   pre_entry:source==='binance'?{symbol:'BTCUSDT',confidence:.65,required_confidence:.70,history_observed:false,observed_at:now}:undefined,
   selection_failure:source==='okx'?{reason:code,error_kind:'network_timeout',attempts:2,observed_at:now}:undefined,
   capital:wallet?{capital_basis:'paper_funds_unverified',reason:'paper_ledger_currency_unverified',available_capital:0,quote_currency:'USDT',observed_at:now}:session?{capital_basis:'paper_reconciled_funds',available_capital:1000,quote_currency:'USDT',paper_session_id:'fixture-session',observed_at:now}:undefined};
 }
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),ep=url.pathname;
  if(!ep.startsWith('/api/')){
   const file=path.join(dist,ep==='/'?'index.html':ep);
   if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png'})[path.extname(file)]||'application/octet-stream'});
   return route.abort();
  }
  if(route.request().method()!=='GET')writes.push(ep);
  const source=url.searchParams.get('source')||'binance';let payload={};
  if(ep.endsWith('/platform'))payload={release_version:'3.9.2.10',release_label:'v3.9.2.10 QA'};
  else if(ep.endsWith('/session'))payload={authenticated:true,account:'entry-fixture',user:{id:'fixture',user_grade:'premium'}};
  else if(ep.endsWith('/features'))payload=inventory;
  else if(ep.endsWith('/runtime/snapshot'))payload={enabled_sources:venues,running_sources:running?venues:[],selected_sources:{blockchain:'binance',stock:'kiwoom'},credential_status:{},paper_trading:true,execution_modes:Object.fromEntries(venues.map(s=>[s,'paper']))};
  else if(ep.endsWith('/settings'))payload={fields:[],revision:'fixture'};
  else if(ep.includes('/workspaces/'))payload={source,trading:{},logs:[],statistics:[],ai_decisions:[],paper_positions:[],operation_summary:evidence(source),operation_overview:Object.fromEntries(venues.map(s=>[s,evidence(s)]))};
  else if(ep.endsWith('/strategies'))payload={strategies:[]};
  else if(ep.endsWith('/logs'))payload={lines:[]};
  else if(ep.endsWith('/maintenance/paper-session')){
   assert.deepEqual(route.request().postDataJSON(),{source:'bybit',new_baseline_acknowledged:true});
   assert.equal(running,false);session=true;payload={created:true,orders_submitted:false,trading_started:false};
  }
  await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
 });
 const capture=async name=>{await page.evaluate(()=>document.fonts.ready);await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});};
 async function openSummary(source){
  await page.locator('.source-tab-strip').getByRole('button',{name:source.toUpperCase(),exact:true}).click();
  const button=page.getByRole('button',{name:'운용 요약',exact:true});
  if(await button.count()&&await page.locator('.operation-summary').count()===0)await button.click();
  await page.getByRole('heading',{name:new RegExp(source.toUpperCase()+'.*운용 요약')}).waitFor();
  await page.locator('.entry-health strong').filter({hasText:evidence(source).entry_health.label}).waitFor();
 }
 try{
  await page.goto('http://127.0.0.1:4218');
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  await page.locator('.operations-venue').last().waitFor();
  assert.match(await page.locator('.operations-overview').innerText(),/과거 PAPER 결제통화 근거 누락/);
  assert.match(await page.locator('.operations-overview').innerText(),/현재 종목 목록 조회 실패/);
  assert.match(await page.locator('.operations-overview').innerText(),/진입 신뢰도 기준 미충족/);
  checks.push('overview exposes downstream blockers while candidate passed');await capture('overview');
  assert.match(await page.locator('.entry-inactivity-alert').innerText(),/COINONE.*30분 이상 신규 주문 처리 기록 없음/);
  checks.push('overview proactively flags long HOLD even without a technical blocker');
  await openSummary('okx');
  assert.match(await page.locator('.operation-summary').innerText(),/공개 목록 응답 시간 초과 · 시도 2회/);
  checks.push('OKX current catalogue cause and retry guidance');await capture('okx');
  await openSummary('binance');
  assert.match(await page.locator('.operation-summary').innerText(),/신뢰도 0.65 \/ 필요 0.70/);
  assert.match(await page.locator('.operation-summary').innerText(),/기본 손실률을 실측값으로 표시하지 않습니다/);
  assert.match(await page.locator('.entry-activity').innerText(),/120분/);
  assert.match(await page.locator('.entry-activity').innerText(),/거래 신호 대기: 70회/);
  assert.match(await page.locator('.entry-activity').innerText(),/진입 신뢰도 기준 미충족: 40회/);
  checks.push('inactivity duration and mixed reason counts visible in venue summary');
  checks.push('actual confidence threshold and missing-history distinction');await capture('binance');
  await openSummary('bybit');
  const action=()=>page.getByRole('button',{name:'과거 기록 보존하고 새 PAPER 평가 준비',exact:true});
  await page.getByLabel('과거 손익 복구가 아니라 별도의 새 PAPER 평가라는 점을 확인했습니다.').check();
  assert.equal(await action().isDisabled(),true);checks.push('running engine cannot start a new PAPER baseline');
  running=false;await page.reload();await page.getByRole('button',{name:'거래 현황',exact:true}).click();await openSummary('bybit');
  await page.getByLabel('과거 손익 복구가 아니라 별도의 새 PAPER 평가라는 점을 확인했습니다.').check();
  await action().click();
  await page.getByText(/새 PAPER 평가 기준을 저장했습니다/).waitFor();
  await page.getByText(/새 PAPER 평가 시작:/).waitFor();
  await page.locator('.entry-health strong').filter({hasText:'새 PAPER 평가 준비됨'}).waitFor();
  assert.equal(await action().count(),0);checks.push('explicit PAPER baseline no start no repeat reset');await capture('paper-session');
  await page.setViewportSize({width:1080,height:850});
  assert(await page.locator('.operation-summary').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  checks.push('summary wraps at supported minimum viewport');
  assert.deepEqual(errors,[]);assert.deepEqual(writes,['/api/v1/maintenance/paper-session']);
  const result={result:'PASS',checks,errors,writes,real_accounts:false,real_orders:0};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
