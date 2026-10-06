// Current built renderer. Every API is intercepted: no real accounts or orders.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const reportDir=path.join(root,'reports/v3926-trading-views-20261006');
const crypto=['binance','upbit','bithumb','coinone','bybit','okx','bitget'],stock=['kiwoom','shinhan','mirae','kis'];
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
(async()=>{
 fs.mkdirSync(reportDir,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 const errors=[],reads=[],writes=[],checks=[], commands=[];
 let failLogs=false,failWorkspace=false,revision=1;const cancelled=new Set();
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})});
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url()),ep=url.pathname;
  if(!ep.startsWith('/api/')){
   const file=path.join(dist,ep==='/'?'index.html':ep);
   if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png'})[path.extname(file)]||'application/octet-stream'});
   return route.abort();
  }
  reads.push({ep,service:url.searchParams.get('service'),source:url.searchParams.get('source')});
  if(route.request().method()!=='GET')writes.push(ep);
  const service=ep.includes('/stock/')||url.searchParams.get('service')==='stock'?'stock':'blockchain';
  const venues=service==='stock'?stock:crypto,source=url.searchParams.get('source')||venues[0];
  const now=Date.now()/1000;
  const evidence=s=>({source:s,mode:'paper',status:'observed',regime:{observed:'bull',confirmed:'range',observed_at:now},candidate:{symbol:service==='stock'?'005930':'BTCUSDT',signal:'HOLD',allowed:false,reason:'custom_entry_failed',observed_at:now},selection:{source:s,observed_at:now,selected:[{symbol:service==='stock'?'005930':'BTCUSDT',score:77,reason:'QA verified liquidity',execution_eligible:true}],eligible_count:1,excluded:['QA-HALTED'],issues:['QA partial catalogue']},orders:{pending_orders:1,requires_reconciliation:true},recovery:{status:cancelled.has(s)?'cancelled_by_user':'restored',fields:['max_retries'],observed_at:now},paper_pool:{scope_eligible:2,selected:2,waiting:0,limit:10,applied_slots:0}});
  let payload={};
  if(ep.endsWith('/runtime/commands')){const body=route.request().postDataJSON();commands.push(body);assert.equal(body.command,'trading.recovery.cancel');cancelled.add(body.source);payload={status:'completed',result:{status:'cancelled_by_user',orders_submitted:false}};}
  else if(ep.endsWith('/platform'))payload={release_version:'3.9.2.6',release_label:'v3.9.2.6 ISOLATED QA'};
  else if(ep.endsWith('/session'))payload={authenticated:true,account:'trading-audit-fixture',user:{id:'fixture',user_grade:'premium'}};
  else if(ep.endsWith('/features'))payload=inventory;
  else if(ep.endsWith('/runtime/snapshot'))payload={status:'attached',enabled_sources:[...crypto,...stock],running_sources:['upbit','kiwoom'],selected_sources:{blockchain:'binance',stock:'kiwoom'},credential_status:Object.fromEntries([...crypto,...stock].map(s=>[s,true])),execution_modes:Object.fromEntries([...crypto,...stock].map(s=>[s,'paper'])),paper_trading:true};
  else if(ep.endsWith('/settings'))payload={fields:[],revision:'fixture'};
  else if(ep.endsWith('/strategies'))payload={strategies:[]};
  else if(ep.includes('/workspaces/')){
   if(failWorkspace)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'QA 통계 연결 실패'})});
   payload={captured_at:new Date().toISOString(),source,trading:{closed_count:0,reconciled_closed_count:0,pnl_by_currency:{}},paper_positions:[],paper_positions_status:'success',paper_statistics:{closed_count:0,pnl_by_currency:{},fees_by_currency:{}},logs:[],statistics:[],ai_decisions:[],operation_overview:Object.fromEntries(venues.map(s=>[s,evidence(s)])),operation_summary:evidence(source)};
  }else if(ep.endsWith('/logs')){
   if(failLogs)return route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'QA 로그 연결 실패'})});
   payload={service,source,captured_at:new Date().toISOString(),lines:[{source:venues[0],exchange:venues[0],level:'INFO',category:'trade',message:`${service} QA 거래 ${revision}`},{source:venues[1],exchange:venues[1],level:'DEBUG',category:'analysis',message:`${service} QA 분석 ${revision}`} ]};
  }else if(ep.endsWith('/runtime/account-snapshot'))payload={sources:{[source]:{status:'success',positions:[]}}};
  await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
 });
 const mark=name=>checks.push(name);
 const logReads=()=>reads.filter(r=>r.ep.endsWith('/logs')).length;
 const capture=async name=>{await page.evaluate(()=>document.fonts.ready);await page.waitForTimeout(200);await page.screenshot({path:path.join(reportDir,name+'.png'),fullPage:true});};
 try{
  await page.goto('http://127.0.0.1:4209');
  for(const [service,label,count]of[['blockchain','블록체인',7],['stock','주식/증권',4]]){
   await page.getByRole('button',{name:label,exact:true}).click();
   await page.getByRole('button',{name:'거래 현황',exact:true}).click();
   await page.locator('.operations-venue').first().waitFor();
   assert.equal(await page.locator('.operations-venue').count(),count);mark(service+' overview venues');
   const before=logReads();await page.waitForTimeout(1200);assert.equal(logReads(),before);mark(service+' hidden logs paused');
   await capture(service+'-overview');
   await page.getByRole('button',{name:'상세 로그',exact:true}).click();
   await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();
   assert.doesNotMatch(await page.locator('.legacy-log-console').innerText(),new RegExp(service==='stock'?'blockchain QA':'stock QA'));mark(service+' isolated logs');
   revision++;await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();mark(service+' logs update');
   await page.getByLabel('디버그 로그 숨김',{exact:true}).check();assert.doesNotMatch(await page.locator('.legacy-log-console').innerText(),/QA 분석/);
   await page.getByLabel('전체 로그',{exact:true}).check();assert.match(await page.locator('.legacy-log-console').innerText(),/QA 분석/);mark(service+' filters');
   await page.locator('.legacy-log-toolbar select').nth(1).selectOption((service==='stock'?stock:crypto)[1].toUpperCase());
   assert.doesNotMatch(await page.locator('.legacy-log-console').innerText(),/QA 거래/);
   await page.locator('.legacy-log-toolbar select').nth(1).selectOption('ALL');
   await page.getByRole('button',{name:'로그지우기',exact:true}).click();assert.doesNotMatch(await page.locator('.legacy-log-console').innerText(),/QA 거래/);
   await page.getByRole('button',{name:'새로고침',exact:true}).click();await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();mark(service+' clear refresh');
   failLogs=true;await page.getByRole('button',{name:'새로고침',exact:true}).click();
   // Error must be visible in the actual log panel, not hidden in collapsed KPI details.
   await page.locator('.legacy-log-card [role="status"]').filter({hasText:'QA 로그 연결 실패'}).waitFor({timeout:5000});mark(service+' visible log failure');
   failLogs=false;await page.getByRole('button',{name:'새로고침',exact:true}).click();await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();
   assert.equal(await page.locator('.legacy-log-card [role="status"]').count(),0);mark(service+' log recovery');
   await capture(service+'-logs');
   await page.getByRole('button',{name:'요약 보기',exact:true}).click();failWorkspace=true;
   await page.getByRole('button',{name:/가상 거래 내역.*PAPER/}).click();
   await page.getByText(/갱신 확인 필요/).waitFor();mark(service+' summary failure');
   failWorkspace=false;await page.getByRole('button',{name:/실거래 내역.*LIVE/}).click();await page.locator('.operations-venue').first().waitFor();
   await page.setViewportSize({width:390,height:844});await capture(service+'-mobile');
   assert(await page.locator('.operations-home-toolbar').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
   assert(await page.evaluate(()=>document.body.scrollWidth>=1080));mark(service+' 390px viewport retains desktop minimum width');
   await page.setViewportSize({width:1440,height:980});
  }
  // Individual venue panels share the same API contract, but their polling is
  // separate from the all-venue summary. Cover one crypto and one broker view.
  for(const [service,label,venue]of[['blockchain','블록체인','BINANCE'],['stock','주식/증권','KIWOOM']]){
   await page.getByRole('button',{name:label,exact:true}).click();
   await page.getByRole('button',{name:'거래 현황',exact:true}).click();
   await page.locator('.source-tab-strip').getByRole('button',{name:venue,exact:true}).click();
   await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();
   failLogs=true;
   await page.locator('.legacy-exchange-log [role="status"]').filter({hasText:'QA 로그 연결 실패'}).waitFor({timeout:5000});
   mark(service+' source log failure visible');failLogs=false;
   await page.locator('.legacy-exchange-log').getByRole('button',{name:'새로고침',exact:true}).click();
   await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();
   await page.getByRole('button',{name:'운용 요약',exact:true}).click();
   await page.locator('.operation-summary').waitFor();
   const before=logReads();await page.waitForTimeout(1200);assert.equal(logReads(),before);mark(service+' source summary pauses logs');
   await page.getByRole('heading',{name:'자동 종목 선정 근거',exact:true}).waitFor();
   await page.getByRole('heading',{name:'주문 접수·체결 대조 필요',exact:true}).waitFor();
   await page.getByText('정상 정책으로 제한 복원 · 다음 주기에 재검증',{exact:true}).waitFor();
   await page.getByText('자료 확인 필요: QA partial catalogue',{exact:true}).waitFor();
   await page.getByText('후보·선정 이유·제외 목록',{exact:true}).click();
   await page.getByText(/QA verified liquidity/).waitFor();
   await page.getByText(/제외: QA-HALTED/).waitFor();mark(service+' selection pending-order and recovery evidence');
   await capture(service+'-source-summary');
   await page.getByRole('button',{name:'이번 실행 정책 복원 취소',exact:true}).click();
   await page.getByText('사용자 취소',{exact:true}).waitFor();mark(service+' explicit safe recovery cancellation');
   await page.getByRole('button',{name:'상세 로그',exact:true}).click();
   await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();mark(service+' source view restoration');
  }
  assert.deepEqual(errors,[]);assert.equal(commands.length,2);assert(commands.every(c=>c.command==='trading.recovery.cancel'));assert.equal(writes.filter(ep=>!ep.endsWith('/runtime/account-snapshot')&&!ep.endsWith('/runtime/commands')).length,0);mark('no order setting strategy AI mutations');
  const result={result:'PASS',checks,errors,writes,commands,requests:reads.length,fixtures:true,real_accounts:false};
  fs.writeFileSync(path.join(reportDir,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){await capture('failure');console.error(reportDir);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
