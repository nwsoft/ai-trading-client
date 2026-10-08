// Current built renderer. Every API is intercepted: no real accounts or orders.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const reportDir=path.join(root,'reports/v3928/ui');
const crypto=['binance','upbit','bithumb','coinone','bybit','okx','bitget'],stock=['kiwoom','shinhan','mirae','kis'];
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
(async()=>{
 fs.mkdirSync(reportDir,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 const errors=[],reads=[],writes=[],checks=[], commands=[];
 let failLogs=false,failWorkspace=false,recoveryBlocked=false,revision=1;const cancelled=new Set(),sessions=new Map();let sessionAttempts=0;
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
  const evidence=s=>{const value=({source:s,mode:'paper',status:'observed',regime:{observed:'bull',confirmed:'range',observed_at:now},candidate:{symbol:service==='stock'?'005930':'BTCUSDT',signal:'HOLD',allowed:false,reason:'custom_entry_failed',observed_at:now},selection:{source:s,observed_at:now,selected:[{symbol:service==='stock'?'005930':'BTCUSDT',score:77,reason:'QA verified liquidity',execution_eligible:true}],eligible_count:1,excluded:['QA-HALTED'],issues:['QA partial catalogue']},capital:sessions.has(s)?{capital_basis:'paper_reconciled_funds',available_capital:1000,quote_currency:'USDT',paper_session_id:sessions.get(s),paper_session_started_at:'2026-10-07T00:00:00Z',observed_at:now}:{capital_basis:'paper_funds_unverified',reason:service==='stock'?'paper_ledger_pnl_unverified':'paper_ledger_currency_unverified',available_capital:0,quote_currency:service==='stock'?'KRW':'USDT',observed_at:now},orders:{pending_orders:1,requires_reconciliation:true,portfolio_exposure:{status:service==='stock'?'blocked':'allowed',reason:service==='stock'?'portfolio_exposure_unverified':'portfolio_exposure_within_limits',observed_at:now,gross_by_currency:service==='stock'?null:{KRW:100000,USDT:950},reference_currency:'KRW',reference_gross:service==='stock'?null:1430000,missing_venues:service==='stock'?['kis']:[],fx:service==='stock'?null:{source:'upbit:USDT/KRW',rate:1400,observed_at:now}}},correlation:{source:s,observed_at:now,candidates:[{symbol:service==='stock'?'005930':'BTCUSDT',avg_correlation:1,correlation_basis:service==='stock'?'correlation_history_unverified':'observed_aligned_daily_returns',correlation_pairs:[{symbol:'QA-PEER',value:service==='stock'?null:.85,samples:service==='stock'?0:99,start:service==='stock'?null:'20260701',end:service==='stock'?null:'20261005'}]}]},recovery:{status:cancelled.has(s)?'cancelled_by_user':'restored',fields:['max_retries'],observed_at:now},paper_pool:{scope_eligible:2,selected:2,waiting:0,limit:10,applied_slots:0}});if(recoveryBlocked)value.capital={capital_basis:'paper_funds_unverified',reason:'paper_close_recovery_required',available_capital:null,quote_currency:'USDT',observed_at:now};return value;};
  let payload={};
  if(ep.endsWith('/maintenance/paper-session')){
   const body=route.request().postDataJSON();assert.equal(body.new_baseline_acknowledged,true);assert.equal(body.source,'binance');sessionAttempts++;
   if(sessionAttempts===1)return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'paper_session_pending_orders'})});
   sessions.set(body.source,'fixture-new-session');payload={created:true,session_id:'fixture-new-session',orders_submitted:false,trading_started:false,historical_pnl_restored:false};
  }else if(ep.endsWith('/runtime/commands')){const body=route.request().postDataJSON();commands.push(body);assert.equal(body.command,'trading.recovery.cancel');cancelled.add(body.source);payload={status:'completed',result:{status:'cancelled_by_user',orders_submitted:false}};}
  else if(ep.endsWith('/platform'))payload={release_version:'3.9.2.8',release_label:'v3.9.2.8 ISOLATED QA'};
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
  await page.getByText('· UI 3.9.2.8',{exact:true}).waitFor();mark('built UI product version matches 3.9.2.8');
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
   await page.getByRole('heading',{name:'자금 배분 근거',exact:true}).waitFor();
   await page.getByRole('heading',{name:'기관 통합 보유 노출',exact:true}).waitFor();
   await page.getByRole('heading',{name:'관측 상관관계와 배분',exact:true}).waitFor();
   await page.getByText(service==='stock'?'통합 노출 확인 필요 · 신규 진입 보류':'당시 통합 노출 한도 이내 · 주문 승인과 별개',{exact:true}).waitFor();
   if(service==='stock')await page.getByText(/확인할 기관: kis/).waitFor();
   else await page.getByText('환산 노출 1,430,000 KRW',{exact:true}).waitFor();
   await page.getByText('종목별 계산 근거',{exact:true}).click();
   await page.getByText(service==='stock'?/상관 자료 부족 · 보수적인 배분/:/배분에 반영한 양의 상관 1.000/).waitFor();
   await page.getByRole('heading',{name:'기관 통합 보유 노출',exact:true}).locator('..').screenshot({path:path.join(reportDir,service+'-global-exposure.png')});
   await page.getByRole('heading',{name:'관측 상관관계와 배분',exact:true}).locator('..').screenshot({path:path.join(reportDir,service+'-observed-correlation.png')});
   mark(service+' observed global exposure and correlation without invented zero');
   await page.getByText('가상 자금 대조 필요 · 신규 진입 보류',{exact:true}).waitFor();
   await page.getByText(service==='stock'?'예약 전 가용액 미확인 KRW':'예약 전 가용액 미확인 USDT',{exact:true}).waitFor();
   await page.getByRole('heading',{name:'자금 배분 근거',exact:true}).locator('..').screenshot({path:path.join(reportDir,service+'-capital-evidence.png')});mark(service+' scoped capital evidence'); await page.getByText(service==='stock'?'과거 PAPER 청산 기록의 손익·비용 근거가 부족하여 자금을 대조할 수 없습니다.':'과거 PAPER 청산 기록의 결제 통화가 누락되어 자금을 대조할 수 없습니다.',{exact:true}).waitFor(); mark(service+' exact legacy capital cause rendered');
   await page.getByRole('heading',{name:'주문 접수·체결 대조 필요',exact:true}).waitFor();
   await page.getByText('정상 정책으로 제한 복원 · 다음 주기에 재검증',{exact:true}).waitFor();
   await page.getByText('자료 확인 필요: QA partial catalogue',{exact:true}).waitFor();
   await page.getByText('후보·선정 이유·제외 목록',{exact:true}).click();
   await page.getByText(/QA verified liquidity/).waitFor();
   await page.getByText(/제외: QA-HALTED/).waitFor();mark(service+' selection pending-order and recovery evidence');
   await capture(service+'-source-summary');
   if(service==='blockchain'){
    recoveryBlocked=true;
    await page.getByText('확정된 PAPER 청산과 잔여 보유량의 저장을 마치지 못했습니다. 저장 상태를 확인한 뒤 다시 실행하세요.',{exact:true}).waitFor({timeout:10000});
    const capital=page.getByRole('heading',{name:'자금 배분 근거',exact:true}).locator('..');
    assert.match(await capital.innerText(),/예약 전 가용액 미확인 USDT/);
    assert.equal(await page.getByRole('button',{name:'과거 기록 보존하고 새 PAPER 평가 준비',exact:true}).count(),0);
    assert.equal(sessionAttempts,0);await capital.screenshot({path:path.join(reportDir,'close-recovery-capital.png')});await capture('close-recovery-blocked');mark('pending close recovery shows unverified funds and cannot start a new baseline');
    recoveryBlocked=false;
    const button=page.getByRole('button',{name:'과거 기록 보존하고 새 PAPER 평가 준비',exact:true});
    assert(await button.isDisabled());assert.equal(sessionAttempts,0);mark('new PAPER session requires separate acknowledgement');
    await page.getByLabel('과거 손익 복구가 아니라 별도의 새 PAPER 평가라는 점을 확인했습니다.',{exact:true}).check();
    await button.click();await page.getByText('주문 예약 또는 처리 중인 작업이 남아 있습니다. 실행 상태를 확인하세요.',{exact:true}).waitFor();
    assert.equal(sessionAttempts,1);mark('new PAPER session blocked action shows concrete guidance');await capture('new-session-reservation-rejected');
    await button.click();await page.getByText(/새 PAPER 평가 기준을 저장했습니다/).waitFor();
    await page.getByText('예약 전 가용액 1,000 USDT',{exact:true}).waitFor();
    await page.getByText(/새 PAPER 평가 시작:/).waitFor();mark('explicit new PAPER session separates history and does not start trading');await capture('new-session-created');
    assert.equal(await button.count(),0);mark('active PAPER session cannot be reset again from summary');
   }else assert.equal(await page.getByRole('button',{name:'과거 기록 보존하고 새 PAPER 평가 준비',exact:true}).count(),0);
   await page.getByRole('button',{name:'이번 실행 정책 복원 취소',exact:true}).click();
   await page.getByText('사용자 취소',{exact:true}).waitFor();mark(service+' explicit safe recovery cancellation');
   await page.getByRole('button',{name:'상세 로그',exact:true}).click();
   await page.getByText(`${service} QA 거래 ${revision}`,{exact:true}).waitFor();mark(service+' source view restoration');
  }
  assert.deepEqual(errors,[]);assert.equal(commands.length,2);assert(commands.every(c=>c.command==='trading.recovery.cancel'));assert.equal(writes.filter(ep=>!ep.endsWith('/runtime/account-snapshot')&&!ep.endsWith('/runtime/commands')&&!ep.endsWith('/maintenance/paper-session')).length,0);assert.equal(sessionAttempts,2);mark('no order setting strategy AI mutations; only explicit PAPER baseline writes');
  const result={result:'PASS',checks,errors,writes,commands,requests:reads.length,fixtures:true,real_accounts:false};
  fs.writeFileSync(path.join(reportDir,'result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }catch(e){await capture('failure');console.error(reportDir);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
