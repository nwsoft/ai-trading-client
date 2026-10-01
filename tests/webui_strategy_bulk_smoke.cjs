// Actual built React UI, synthetic data only; all external traffic blocked.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'}),reports=fs.mkdtempSync(path.join(os.tmpdir(),'noah-bulk-'));
 try {
  const page=await browser.newPage({viewport:{width:1440,height:1000},acceptDownloads:true});
  const errors=[],writes=[],exports=[];let hold=false;
  let rows=['approved','analyzed','paper_observing','active'].map((status,i)=>({scope:'unified',strategy_key:`fixture-${i}`,versions:[{strategy_key:`fixture-${i}`,version_id:`v${i}`,version:1,name:`테스트 ${i}`,status,active:status==='active',paper_observing:status==='paper_observing',rules:{target_scope:'asset:crypto'},missing_conditions:[],xai:{summary:'모의 시험'},guidance:{},execution_readiness:{ready:true}}]}));
  page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.addInitScript(()=>{window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})};});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url()),ep=url.pathname;
   if(url.origin!=='http://127.0.0.1:4209')return route.abort();
   if(!ep.startsWith('/api/')){
    const file=path.join(dist,ep==='/'?'index.html':ep);
    return fs.existsSync(file)&&fs.statSync(file).isFile()?route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html'})[path.extname(file)]||'application/octet-stream'}):route.abort();
   }
   let data={};
   if(ep.endsWith('/session'))data={authenticated:true,account:'bulk-fixture',user:{id:'fixture',user_grade:'premium'}};
   else if(ep.endsWith('/platform'))data={release_version:'3.9.2.0'};
   else if(ep.endsWith('/features'))data=inventory;
   else if(ep.endsWith('/settings'))data={fields:[],revision:'fixture'};
   else if(ep.endsWith('/runtime/snapshot'))data={status:'attached',enabled_sources:['binance'],running_sources:[],paper_trading:true};
   else if(ep.endsWith('/strategies')&&req.method()==='GET')data={strategies:rows};
   else if(ep.endsWith('/strategies/actions')){
    const body=req.postDataJSON();writes.push(body);if(hold)await new Promise(r=>setTimeout(r,700));
    const v=rows.find(r=>r.strategy_key===body.strategy_key)?.versions[0];
    if(body.action==='start_paper'&&body.strategy_key==='fixture-0')return route.fulfill({status:409,contentType:'application/json',body:JSON.stringify({detail:'다른 버전 상태를 먼저 확인하세요.'})});
    if(v){v.active=false;v.paper_observing=false;v.status=body.action==='stop_paper'?'paper_paused':'approved';}
   }else if(ep.endsWith('/package')){exports.push(url.searchParams.get('definition_only'));data={package_json:JSON.stringify({format:'fixture-only',passport:url.searchParams.has('definition_only')?{}:{fixture:true}})};}
   else if(req.method()==='DELETE'&&ep.endsWith('/strategies')){const body=req.postDataJSON();writes.push({delete:body});rows=rows.filter(r=>r.strategy_key!==body.strategy_key);}
   else if(ep.endsWith('/logs'))data={lines:[]};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto('http://127.0.0.1:4209');
  await page.getByLabel('블록체인 세부 기능').getByRole('button',{name:'전략 스튜디오',exact:true}).click();
  const bulk=page.getByRole('region',{name:'선택 전략 작업'});
  await page.locator('.strategy-version-select input').first().waitFor();
  assert.equal(await page.locator('.strategy-version-select input').count(),4);
  await bulk.getByRole('button',{name:'현재 목록 선택',exact:true}).click();
  await page.getByRole('textbox',{name:'전략 검색',exact:true}).fill('테스트 0');
  await bulk.getByText('0개 버전 선택',{exact:true}).waitFor();
  await page.getByRole('textbox',{name:'전략 검색',exact:true}).fill('');
  await bulk.getByRole('button',{name:'현재 목록 선택',exact:true}).click();
  await bulk.getByRole('button',{name:'선택 PAPER 검증',exact:true}).click();
  await bulk.getByText('처리 완료 · 아래 개별 결과를 확인하세요.',{exact:true}).waitFor();
  assert.equal(writes.length,1);assert.equal(writes[0].action,'start_paper');assert.equal(writes[0].live_confirmation,false);
  assert.match(await bulk.innerText(),/실패·상태 확인/);assert.match(await bulk.innerText(),/사용자 승인/);
  await bulk.getByRole('button',{name:'현재 목록 선택',exact:true}).click();
  await bulk.getByRole('button',{name:'선택 버전 삭제',exact:true}).click();
  await bulk.getByText('처리 완료 · 아래 개별 결과를 확인하세요.',{exact:true}).waitFor();
  assert.equal(writes.filter(r=>r.delete).length,2,'active/PAPER versions not deleted');
  await page.locator('.strategy-version-select input').first().waitFor();
  for(const [label,definition] of [['선택 전략 내보내기','true'],['선택 패키지 내보내기',null]]){
   await bulk.getByRole('button',{name:'현재 목록 선택',exact:true}).click();await bulk.getByRole('button',{name:label,exact:true}).click();
   const link=bulk.getByRole('link',{name:'준비된 ZIP 다운로드'});await link.waitFor();
   const pending=page.waitForEvent('download');await link.click();const dl=await pending;await dl.saveAs(path.join(reports,dl.suggestedFilename()));
   assert.deepEqual(exports.slice(-2),[definition,definition]);
  }
  // Cancellation stops the next mutation, not a request already sent.
  hold=true;await bulk.getByRole('button',{name:'현재 목록 선택',exact:true}).click();
  const before=writes.length;await bulk.getByRole('button',{name:'선택 일시중지',exact:true}).click();
  await bulk.getByRole('button',{name:'남은 작업 중단'}).click();await bulk.getByText(/중단됨 ·/).waitFor();
  assert.equal(writes.length,before+1);assert.match(await bulk.innerText(),/미실행/);
  for(const width of [1440,1080]){
   await page.setViewportSize({width,height:1000});await bulk.scrollIntoViewIfNeeded();
   assert(await bulk.evaluate(e=>e.scrollWidth<=e.clientWidth+1),'bulk toolbar wraps');
   await page.screenshot({path:path.join(reports,`bulk-${width}.png`)});
  }
  assert.deepEqual(errors,[]);assert(!writes.some(r=>r.action==='approve'||r.action==='activate'||r.action==='restart_paper'));
  console.log(JSON.stringify({ok:true,errors,writes:writes.length,exports:exports.length,reports}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
