// Actual React UI; every API is synthetic. Never connects to a trading account.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs=require('node:fs'), path=require('node:path'), os=require('node:os'), assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
const sectionNames=['일반','거래소 선택','거래소 API','AI 엔진/API','알림·리포트','고급 매매 계층','AlphaArena','AI 시스템 상태','업데이트'];
const field=(path,value,section,kind='text',options=[])=>({path,value,section,kind,options,label:'화면 점검 · '+path,help:'설명의 크기와 입력 위치를 점검합니다. 저장 또는 실제 주문을 실행하지 않습니다.',presentation:'primary',risk:'low'});
const fields=[field('paper_trading',true,'general','boolean'),field('log_level','INFO','general','select',['INFO','DEBUG']),
 field('enabled_exchanges',['binance'],'exchange_selection','multiselect',['binance','upbit','bithumb','coinone','bybit','okx','bitget']),
 field('trade_enabled_exchanges',[],'exchange_selection','multiselect',['binance','upbit','bithumb','coinone','bybit','okx','bitget']),
 ...['ai_engine','notifications','advanced','alpha','system','update'].map(section=>field('fixture_'+section,true,section,'boolean'))];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 const errors=[], writes=[], measurements=[];
 const reports=fs.mkdtempSync(path.join(os.tmpdir(),'noah-v49-layout-'));
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})};
  localStorage.setItem('noahai.strategy-studio-guided.blockchain','done');
 });
 // Optional built renderer route: verifies dist, not only the development server.
 if(process.env.NOAHAI_QA_DIST) await page.route('**/*',async route=>{
  const url=new URL(route.request().url());
  if(url.pathname.startsWith('/api/')) return route.fallback();
  const target=path.join(process.env.NOAHAI_QA_DIST,url.pathname==='/'?'index.html':url.pathname);
  const types={'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.svg':'image/svg+xml'};
  if(fs.existsSync(target)&&fs.statSync(target).isFile()) return route.fulfill({body:fs.readFileSync(target),contentType:types[path.extname(target)]||'application/octet-stream'});
  return route.abort();
 });
 await page.route('**/api/v1/**',async route=>{
  const endpoint=new URL(route.request().url()).pathname;
  if(route.request().method()!=='GET') writes.push(endpoint);
  let payload={};
  if(endpoint.endsWith('/platform')) payload={release_version:'3.9.1.50',release_label:'v3.9.1.50 QA'};
  else if(endpoint.endsWith('/session')) payload={authenticated:true,account:'layout-fixture',user:{id:'fixture',user_grade:'premium'}};
  else if(endpoint.endsWith('/features')) payload=inventory;
  else if(endpoint.endsWith('/runtime/snapshot')) payload={enabled_sources:['binance'],running_sources:[],selected_sources:{blockchain:'binance'},credential_status:{},paper_trading:true,execution_modes:{binance:'paper'}};
  else if(endpoint.endsWith('/settings')) payload={fields,revision:'fixture',credential_status:{binance:true,upbit:false,bithumb:false,coinone:false,bybit:false,okx:false,bitget:false,'stock:kiwoom':false,'stock:shinhan':false,'stock:miraeasset':false,'stock:kis':false,'ai:openai':true,'ai:deepseek':false,'alpha:deepseek':false},model_catalog_details:{openai:Array.from({length:8},(_,i)=>({model:`QA model ${i}`,label:`테스트 모델 ${i}`,status_label:'권장',use:'로컬 화면 시험',capabilities:['chat','json'],strength:'긴 한글 설명도 읽기 쉬운 크기로 표시합니다.',limitation:'실제 모델이나 계정 검증 자료가 아닙니다.',input_per_mtok_usd:1,output_per_mtok_usd:2}))}};
  else if(endpoint.endsWith('/strategies')) payload={strategies:[]};
  else if(endpoint.includes('/workspaces/')) payload={source:'binance',trading:{},logs:[],statistics:[],ai_decisions:[],paper_positions:[]};
  else if(endpoint.endsWith('/logs')) payload={lines:[]};
  else if(endpoint.includes('audit')) payload={records:[]};
  await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
 });
 try{
  await page.goto(process.env.NOAHAI_QA_URL||'http://127.0.0.1:4209');
  await page.getByRole('button',{name:'거래 현황',exact:true}).click();
  await page.getByRole('button',{name:'BINANCE',exact:true}).click();
  await page.getByRole('button',{name:'운용 요약',exact:true}).click();
  await page.locator('.operation-summary').waitFor();
  assert.match(await page.locator('.operation-summary').innerText(),/근거가 아직 없습니다/);
  await page.screenshot({path:path.join(reports,'summary.png')});
  await page.getByRole('button',{name:'상세 로그',exact:true}).click();
  await page.getByRole('button',{name:'전략 스튜디오',exact:true}).click();
  const controls=page.getByTestId('strategy-list-controls');
  await controls.scrollIntoViewIfNeeded();
  for(const width of [1440,1080,900]){
   await page.setViewportSize({width,height:900});
   await controls.scrollIntoViewIfNeeded();
   assert.ok(await controls.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
   const control=await controls.locator('select').first().evaluate(e=>({font:parseFloat(getComputedStyle(e).fontSize),height:e.getBoundingClientRect().height}));
   assert.ok(control.font>=14 && control.height>=41,JSON.stringify(control));
   await page.screenshot({path:path.join(reports,`strategy-${width}.png`)});
  }
  await controls.locator('input').fill('시험');
  await controls.getByRole('button',{name:'검색·필터 초기화'}).click();
  assert.equal(await controls.locator('input').inputValue(),'');
  // All services retain their own conversation but fill the same main viewport.
  for(const width of [1440,1080]){
   await page.setViewportSize({width,height:900});
   const nav=page.locator('.legacy-topbar .service-nav');
   for(const button of await nav.locator('button').all())assert.ok(await button.evaluate(e=>{const b=e.getBoundingClientRect(),n=e.closest('nav').getBoundingClientRect();return b.x>=n.x-1&&b.right<=n.right+1&&b.y>=n.y-1&&b.bottom<=n.bottom+1;}),'all main services remain visible instead of clipping');
   for(const service of ['블록체인','AI애널리스트']){
    await page.getByRole('button',{name:service,exact:true}).click();
    await page.getByRole('button',{name:'AI 어시스턴트',exact:true}).click();
    const panel=page.locator('.assistant-view:not([hidden]) .legacy-assistant-workspace');
    await panel.waitFor();
    const tools=panel.locator('.assistant-info-bar');
    for(const control of await tools.locator('button,select').all()) {
     const size=await control.evaluate(e=>({font:parseFloat(getComputedStyle(e).fontSize),height:e.getBoundingClientRect().height}));
     assert.ok(size.font<=11 && size.height<=32,`assistant toolbar must stay compact: ${JSON.stringify(size)}`);
    }
    assert.equal(await tools.getByRole('combobox',{name:'설명 수준'}).count(),1);
    assert.equal(await panel.locator('.legacy-quick-question-panel').getByRole('combobox',{name:'설명 수준'}).count(),0);
    await tools.getByRole('combobox',{name:'설명 수준'}).selectOption('advanced');
    await tools.getByRole('button',{name:'심층분석',exact:true}).click();
    assert.ok((await tools.getByRole('button',{name:'심층분석',exact:true}).getAttribute('class')).includes('active'));
    await tools.getByRole('button',{name:'일반 안내',exact:true}).click();
    assert.equal(await tools.getByRole('combobox',{name:'설명 수준'}).inputValue(),'advanced');
    assert.ok(await tools.evaluate(e=>e.scrollWidth<=e.clientWidth+1));
    const box=await panel.boundingBox(), main=await page.locator('.legacy-content-frame > main').boundingBox();
    assert.ok(box.x+box.width<=width,'assistant fits supported desktop width');
    assert.ok(box.height/main.height>0.9,`${service}: ${box.height}/${main.height}`);
    const input=await panel.locator('.legacy-chat-input').boundingBox();
    assert.ok(input.y+input.height<=main.y+main.height+1,'input visible within workspace');
    measurements.push({width,service,panelHeight:box.height,mainHeight:main.height});
    await page.screenshot({path:path.join(reports,`assistant-${service}-${width}.png`)});
   }
  }
  await page.getByRole('button',{name:'설정',exact:true}).click();
  // All nine tabs, including synthetic long provider names and multi-select rows.
  for(const width of [1440,1080,900]){
   const height=width===900?700:980;await page.setViewportSize({width,height});
   for(const name of sectionNames){
    await page.locator('.settings-section-tabs').getByRole('button',{name,exact:true}).click();
    const body=page.locator('.settings-fields');
    await body.evaluate(e=>e.scrollTop=0);
    assert.ok(await body.evaluate(e=>e.scrollWidth<=e.clientWidth+1),`${name} horizontal overflow at ${width}`);
    const footer=await page.locator('.settings-center > footer').boundingBox();
    assert.ok(footer.y+footer.height<=height,`${name} footer visible at ${width}`);
    assert.ok(await body.locator('.settings-tab-commandbar p').evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=14));
    for(const p of await body.locator('.setting-row p, .credential-selected-state small').all()) assert.ok(await p.evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=14));
    if(name==='거래소 선택'){
     const row=body.locator('[data-setting-path="enabled_exchanges"]');await row.scrollIntoViewIfNeeded();
     const group=await row.locator('.setting-multiselect').boundingBox(), rb=await row.boundingBox();
     assert.ok(group.width/rb.width>.9,'choices use row width, not legacy 190px column');
     assert.equal(await row.locator('input:checked').count(),1);
     assert.equal(await body.locator('[data-setting-path="trade_enabled_exchanges"] input:disabled').count(),6);
    }
    await page.screenshot({path:path.join(reports,`tab-${name.replaceAll('/','-')}-${width}.png`)});
   }
  }
  await page.getByRole('button',{name:'AI 엔진/API',exact:true}).click();
  const dialog=page.locator('.settings-center');
  const grid=page.locator('.settings-ai-model-grid');
  await grid.waitFor();
  for(const width of [1440,1080,900]){
   const height=width===900?700:900;
   await page.setViewportSize({width,height});
   await grid.scrollIntoViewIfNeeded();
   const box=await dialog.boundingBox();
   assert.ok(box.x>=0&&box.x+box.width<=width,'dialog fits viewport');
   if(width===1440) assert.ok(box.width>=1200,'desktop settings enlarged');
   assert.ok(await grid.locator('p').first().evaluate(e=>parseFloat(getComputedStyle(e).fontSize)>=14));
   assert.ok(await grid.evaluate(e=>e.scrollHeight<=e.clientHeight+1),'model catalog does not have nested clipping');
   const footer=await page.locator('.settings-center > footer').boundingBox();
   assert.ok(footer.y+footer.height<=height,'footer remains visible');
   await page.screenshot({path:path.join(reports,`settings-${width}.png`)});
  }
  assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  console.log(JSON.stringify({result:'PASS',reports,measurements,errors,writes}));
 }catch(error){console.error((await page.locator('body').innerText()).slice(-2500));await page.screenshot({path:path.join(reports,'failure.png')});console.error(reports);throw error;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
