// Built React renderer only. All network paths are intercepted; no account/order access.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=process.env.NOAHAI_QA_DIST||path.join(root,'webui/dist');
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
const crypto=['binance','upbit','bithumb','coinone','bybit','okx','bitget'],stock=['kiwoom','shinhan','mirae','kis'];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 // Let compositor finish resizing before inspecting captured pixels.
 const capture=async options=>{await page.waitForTimeout(150);return page.screenshot({...options,animations:'disabled'});};
 const errors=[],requests=[],writes=[],commands=[];
 const reports=fs.mkdtempSync(path.join(os.tmpdir(),'noah-v50-home-'));
 let slowLive=false,missing=false,failWorkspace=false,neutral=false,selected=crypto,emptyTrades=false,failAccounts=false,startRefusal='',mismatched=false;
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})};});
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),ep=url.pathname;
  if(!ep.startsWith('/api/')){
   const file=path.join(dist,ep==='/'?'index.html':ep);
   if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json'})[path.extname(file)]||'application/octet-stream'});
   return route.abort();
  }
  requests.push(ep);if(route.request().method()!=='GET')writes.push(ep);
  const now=Date.now()/1000;let payload={};
  const modeFor=s=>!neutral&&(s==='binance'||s==='kiwoom')?'live':'paper';
  const evidence=s=>({source:s,mode:modeFor(s),status:'observed',regime:{observed:'bull',confirmed:'range',observed_at:now},regime_history:[{observed:'range',confirmed:'range',symbol:'X',timeframe:'5m',observed_at:now-300},{observed:'bull',confirmed:'bull',symbol:'X',timeframe:'5m',observed_at:now}],candidate:{symbol:'TEST',strategy_name:'실제 조건 시험',version_id:'v1',allowed:false,observed_at:now,checks:[{passed:true,reason:'검사 1'},{passed:false,reason:'검사 2'}]},paper_pool:{scope_eligible:40,selected:30,waiting:10,limit:30,applied_slots:0},risk:{blocked:s==='binance',reason_code:'pnl_reconciliation_required',observed_at:now}});
  if(ep.endsWith('/platform'))payload={release_version:'3.9.1.50',release_label:'v3.9.1.50 QA'};
  else if(ep.endsWith('/session'))payload={authenticated:true,account:'home-fixture',user:{id:'fixture',user_grade:'premium'}};
  else if(ep.endsWith('/features'))payload=inventory;
  else if(ep.endsWith('/runtime/snapshot'))payload={status:'attached',captured_at:new Date().toISOString(),enabled_sources:[...selected,...stock],running_sources:neutral?[]:['upbit'],selected_sources:{blockchain:selected[0]||'binance',stock:'kiwoom'},credential_status:Object.fromEntries([...crypto,...stock].map(s=>[s,!neutral])),execution_modes:Object.fromEntries([...crypto,...stock].map(s=>[s,modeFor(s)])),paper_trading:true};
  else if(ep.endsWith('/settings'))payload={fields:[],revision:'fixture'};
  else if(ep.endsWith('/strategies'))payload={strategies:[]};
  else if(ep.includes('/workspaces/')){
   if(failWorkspace)return route.fulfill({status:503,body:'{}',contentType:'application/json'});
   const service=ep.includes('/stock/')?'stock':'blockchain',source=url.searchParams.get('source')||(service==='stock'?'kiwoom':'upbit'),mode=url.searchParams.get('statistics_mode');
   payload={captured_at:new Date().toISOString(),source,trading:missing?{}:{closed_count:emptyTrades?0:3,reconciled_closed_count:emptyTrades?0:2,unresolved_closed_count:emptyTrades?0:1,win_rate:50,open_position_count:2,pnl_by_currency:{[service==='stock'?'KRW':'USDT']:mode==='live'?987:123}},paper_positions:[],logs:[],statistics:[],ai_decisions:[],operation_overview:neutral?{}:Object.fromEntries((service==='stock'?stock:crypto).map(s=>[s,evidence(s)])),operation_summary:neutral?undefined:evidence(source)};
   if(mismatched)for(const row of Object.values(payload.operation_overview))row.mode='learning';
   if(slowLive&&mode==='live')await new Promise(r=>setTimeout(r,1000));
  }
  else if(ep.endsWith('/logs'))payload={lines:[{source:'fixture',message:'FIXTURE 상세 로그',level:'INFO'}]};
  else if(ep.endsWith('/runtime/account-snapshot')){if(failAccounts)return route.fulfill({status:503,body:'{}',contentType:'application/json'});await new Promise(r=>setTimeout(r,200));payload={sources:Object.fromEntries([...crypto,...stock].map(s=>[s,{status:'success',positions:[{symbol:'FIXTURE'}]}]))};}
  else if(ep.endsWith('/runtime/commands')){const body=route.request().postDataJSON();commands.push(body);if(startRefusal)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:startRefusal})});await new Promise(r=>setTimeout(r,100));payload={accepted:true,result:{}};}
  else if(ep.includes('audit'))payload={records:[]};
  await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
 });
 try{
  await page.goto('http://127.0.0.1:4209');
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  assert.match(await page.locator('.legacy-release').getAttribute('title'),/20260930\.1/);
  await page.locator('.operations-venue').first().waitFor();
  assert.equal(await page.locator('.operations-venue').count(),7);
  await page.locator('.visual-insight-grid').waitFor();
  assert.equal(await page.locator('.visual-insight-grid > article').count(),3);
  assert.equal(await page.locator('.visual-overview .regime-sample').count(),2);
  assert.match(await page.locator('.visual-check-chart').getAttribute('aria-label'),/충족 1, 미충족 1/);
  const beforeChoice=requests.length;
  await page.getByRole('group',{name:'분석 기관 선택'}).getByRole('button',{name:'OKX',exact:true}).click();
  assert.match(await page.locator('.visual-context').innerText(),/OKX · PAPER/);
  assert.equal(requests.length,beforeChoice,'visual selection reuses existing snapshots');
  assert.match(await page.locator('.operations-attention').innerText(),/신규 진입 보류[\s\S]*BINANCE/);
  assert.equal(await page.getByRole('button',{name:/실거래 내역.*LIVE/}).getAttribute('aria-pressed'),'true');
  assert.equal(writes.filter(p=>p.endsWith('/runtime/account-snapshot')).length,0,'LIVE view never auto-fetches private accounts');
  const logCount=()=>requests.filter(p=>p.endsWith('/logs')).length;
  const initial=logCount();await page.waitForTimeout(1500);assert.equal(logCount(),initial,'overview does not fetch hidden log');
  for(const width of[1440,1080]){
   await page.setViewportSize({width,height:900});
   for(const selector of['.operations-home-toolbar','.operations-overview','.dashboard-statistics','.dashboard-venue-table'])assert.ok(await page.locator(selector).evaluate(e=>e.scrollWidth<=e.clientWidth+1),selector+' wraps');
   assert.equal(await page.locator('.legacy-operations-column').count(),0,'overview has no separate sidebar scroller');
   await capture({path:path.join(reports,`overview-${width}.png`)});
  }
  await page.getByRole('button',{name:'상세 로그',exact:true}).click();
  await page.getByText('FIXTURE 상세 로그',{exact:true}).waitFor();
  await page.getByRole('button',{name:'요약 보기',exact:true}).click();
  const stopped=logCount();await page.waitForTimeout(1500);assert.equal(logCount(),stopped);
  // Late LIVE data must not overwrite the newly selected PAPER scope.
  const mode={selectOption:async value=>page.getByRole('button',{name:value==='live'?/실거래 내역.*LIVE/:/가상 거래 내역.*PAPER/}).click()};
  await mode.selectOption('paper');slowLive=true;
  await mode.selectOption('live');await page.waitForTimeout(100);await mode.selectOption('paper');await page.waitForTimeout(1300);
  assert.match(await page.locator('.legacy-kpi-grid').innerText(),/123/);
  assert.doesNotMatch(await page.locator('.legacy-kpi-grid').innerText(),/987/);slowLive=false;
  missing=true;await mode.selectOption('live');await page.waitForTimeout(250);
  assert.match(await page.locator('.legacy-kpi-grid').innerText(),/확인 중|대조 전/);
  assert.doesNotMatch(await page.locator('.legacy-kpi-grid').innerText(),/0\.00%|\+0 USDT/);missing=false;
  assert.equal(writes.filter(p=>p.endsWith('/runtime/account-snapshot')).length,0);
  await page.locator('.dashboard-statistics details > summary').click();
  failAccounts=true;await page.getByRole('button',{name:'현재 계좌 확인',exact:true}).click();
  await page.getByText(/통계 또는 계좌 갱신에 실패/).waitFor();failAccounts=false;
  await page.getByRole('button',{name:'현재 계좌 확인',exact:true}).click();
  await page.getByRole('button',{name:'현재 계좌 확인',exact:true}).waitFor();
  assert.match(await page.locator('.dashboard-kpis').innerText(),/조회 시점 계좌 포지션\s+7/,'count only requested crypto venues, not all returned venues');
  assert.equal(writes.filter(p=>p.endsWith('/runtime/account-snapshot')).length,2,'explicit check only');
  await page.locator('.dashboard-statistics details > summary').click();
  // Cancel and then confirm synthetic mixed-mode batch: no safety bypass.
  page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'설정 대상 전체 시작',exact:true}).click();assert.equal(commands.length,0);
  let confirmation='';page.once('dialog',async d=>{confirmation=d.message();await d.accept();});
  await page.getByRole('button',{name:'설정 대상 전체 시작',exact:true}).click();
  await page.getByText(/요청 처리됨 · 실제 실행 상태는 기관 상세 확인/).waitFor();
  assert.match(confirmation,/BINANCE · LIVE/);assert.match(confirmation,/COINONE · PAPER/);
  assert.equal(commands.length,6);assert.equal(commands.find(c=>c.source==='binance').live_confirmation,true);assert.equal(commands.find(c=>c.source==='coinone').live_confirmation,false);
  // Venue card opens existing detailed workspace; graphs are actual fixture evidence.
  await page.locator('.operations-venue').filter({has:page.getByText('UPBIT',{exact:true})}).getByRole('button').click();
  await page.getByRole('button',{name:'운용 요약',exact:true}).click();
  await page.locator('.regime-history-track').waitFor();
  assert.equal(await page.locator('.regime-sample').count(),2);
  assert.match(await page.locator('.operation-summary').innerText(),/표시된 검사 2개 중 충족 1개/);
  await page.screenshot({path:path.join(reports,'source-summary.png')});
  // A real rendered start command preserves the original reason and does not
  // query unrelated LIVE recovery state for PAPER failures.
  await page.getByRole('button',{name:'OKX',exact:true}).click();
  for(const code of ['exchange_initialization_failed:okx:initialization','trading_candidates_unavailable:okx:candidate_selection','runtime_start_exception:okx:worker_start','runtime_source_stopping:okx:worker_start','runtime_start_cancelled:okx:worker_start']){
   startRefusal=code;
   page.once('dialog',d=>d.accept());await page.getByRole('button',{name:'▶ OKX 거래 시작',exact:true}).click();
   await page.locator('.trading-start-help').waitFor();
   await page.getByRole('button',{name:'Q&A·관리자용 진단 만들기',exact:true}).click();
   const report=await page.locator('.trading-start-help textarea').inputValue();
   assert.ok(report.includes('지원 코드: '+code.split(':')[0]));
   assert.ok(report.includes('실패 단계: '+code.split(':')[2]));
   assert.ok(report.includes(commands.at(-1).command_id));
   assert.doesNotMatch(report,/start_refused_check_displayed_reason|복구 완료 후 시작/);
   assert.equal(await page.locator('.trading-start-help details').count(),0);
  }
  assert.equal(requests.filter(p=>p.includes('/maintenance/trade-records')).length,0);
  await page.locator('.trading-start-help').evaluate(e=>e.scrollTop=0);
  await page.screenshot({path:path.join(reports,'okx-paper-diagnostic.png')});startRefusal='';
  await page.getByRole('button',{name:'주식/증권',exact:true}).click();
  await page.locator('.operations-venue').first().waitFor();assert.equal(await page.locator('.operations-venue').count(),4);
  await page.screenshot({path:path.join(reports,'stock-overview.png')});
  failWorkspace=true;await mode.selectOption('paper');
  await page.getByText(/갱신 확인 필요/).waitFor();failWorkspace=false;
  await page.getByRole('button',{name:'이 현황 AI에게 묻기',exact:true}).click();
  await page.locator('.assistant-view:not([hidden])').waitFor();
  assert.deepEqual(writes.filter(p=>!p.endsWith('/runtime/account-snapshot')&&!p.endsWith('/runtime/commands')),[],'read-only navigation cannot submit AI/settings/strategies');
  // Other execution modes cannot be borrowed to fill the visual cards.
  mismatched=true;await page.reload();await page.getByRole('button',{name:'블록체인',exact:true}).click();
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  await page.locator('.visual-overview').waitFor();
  assert.equal(await page.locator('.visual-overview .regime-sample').count(),0);
  assert.equal(await page.locator('.visual-check-chart').count(),0);
  assert.doesNotMatch(await page.locator('.visual-strategy').innerText(),/실제 조건 시험/);mismatched=false;
  // Stopped/unconfigured is neutral; the visual placeholders remain explicit.
  neutral=true;emptyTrades=true;await page.reload();
  await page.getByRole('button',{name:'블록체인',exact:true}).click();
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  await page.locator('.operations-venue').first().waitFor();
  assert.equal(await page.getByRole('button',{name:/실거래 내역.*LIVE/}).getAttribute('aria-pressed'),'true','blockchain preference is distinct from stocks PAPER');
  assert.equal(await page.locator('.operations-attention').count(),0);
  assert.match(await page.locator('.dashboard-kpis').innerText(),/청산 없음/);
  for(const width of [1440,1080,900]){
   await page.setViewportSize({width,height:900});await capture({path:path.join(reports,`neutral-${width}.png`)});
   assert.ok(await page.locator('.dashboard-overview').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
   assert.equal(await page.locator('.visual-overview .regime-state-orbit').innerText(),'확정 국면\n미확인');
   assert.equal(await page.locator('.visual-check-chart').count(),0,'empty evidence is not a fabricated chart');
  }
  await mode.selectOption('paper');await page.reload();
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  assert.equal(await page.getByRole('button',{name:/가상 거래 내역.*PAPER/}).getAttribute('aria-pressed'),'true','last statistics selection persists');
  selected=['binance'];await page.reload();await page.getByRole('button',{name:'거래 현황',exact:true}).click();await page.locator('.operations-venue').first().waitFor();
  assert.equal(await page.locator('.operations-venue').count(),1);await page.screenshot({path:path.join(reports,'single.png')});
  selected=[];await page.reload();await page.getByRole('button',{name:'거래 현황',exact:true}).click();await page.locator('.dashboard-empty').waitFor();
  assert.equal(await page.locator('.operations-attention').count(),0);await page.screenshot({path:path.join(reports,'empty.png')});
  await page.evaluate(()=>localStorage.setItem('noahai.locale.home-fixture','en'));
  await page.setViewportSize({width:1440,height:980});
  await page.reload();
  await page.getByRole('button',{name:'Trading overview',exact:true}).click();
  await page.getByRole('button',{name:'Overview',exact:true}).waitFor();
  await page.getByRole('button',{name:'Detailed logs',exact:true}).waitFor();
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({result:'PASS',reports,commands:commands.length,errors}));
 }catch(e){await page.screenshot({path:path.join(reports,'failure.png')});console.error(reports);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
