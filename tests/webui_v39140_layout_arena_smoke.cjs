const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');const fs=require('fs');const {execFileSync}=require('child_process');
const assert=require('node:assert/strict');const base=process.env.QA_BASE||'http://127.0.0.1:4199',out=process.env.AUDIT_DIR;
const inventory=JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
const analysis=JSON.parse(execFileSync('.venv/bin/python',['-c','import json;from trading.strategy_source_ingestor import StrategySourceIngestor;print(json.dumps(StrategySourceIngestor().analyze("RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%. 횡보장에서 사용.","text"),ensure_ascii=False))'],{encoding:'utf8'}));
(async()=>{const browser=await chromium.launch({headless:true});const result={};try{const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(10000);let available=true,running=false;result.errors=[];result.commands=[];
page.on('pageerror',e=>result.errors.push(e.message));
await page.addInitScript(()=>{window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'isolated-layout',desktop:false})};localStorage.setItem('noahai.strategy-studio-guided.blockchain','done');localStorage.setItem('noahai.strategy-studio-guided.stock','done')});
await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();const p=u.pathname;if(!p.startsWith('/api/'))return route.continue();let x={};
if(p.endsWith('/platform'))x={release_version:'3.9.1.40'};
else if(p.endsWith('/session'))x={authenticated:true,user:{id:'QA',user_grade:'premium'}};
else if(p.endsWith('/features'))x=inventory;
else if(p.endsWith('/settings'))x={fields:[{path:'alpha_arena.enabled',value:true},{path:'ai_custom_features.profile',value:'beginner'},{path:'paper_trading',value:true}],revision:'qa'};
else if(p.endsWith('/runtime/snapshot'))x={enabled_sources:['binance','upbit','kis'],running_sources:[],selected_sources:{blockchain:'binance',stock:'kis'},credential_status:{},paper_trading:true};
else if(p.endsWith('/strategies/source-analysis'))x=analysis;
else if(p.endsWith('/strategies'))x={strategies:[]};
else if(p.includes('/alpha-arena')){if(route.request().method()!=='GET'){result.commands.push(route.request().postDataJSON());running=route.request().postDataJSON().action==='start';}x={available,running,paper_trading:true,execution_mode:'PAPER',events:[{at:'2026-09-19T00:00:00Z',kind:'model_chat',payload:'VISIBLE_MODEL_EXPLANATION'},{at:'2026-09-19T00:00:01Z',kind:'decision',payload:{BTC:{signal:'ENTER_LONG',risk_usd:10}}},{at:'2026-09-19T00:00:02Z',kind:'paper_result',payload:{symbol:'BTCUSDT',result:{status:'SIMULATED',mode:'PAPER',order_submitted:false}}}]};if(route.request().method()!=='GET')x={result:x};}
else if(p.endsWith('/logs'))x={lines:[],entries:[],sources:[],categories:[],levels:[]};
else if(p.includes('/workspaces/'))x={trading:{},logs:[],statistics:[],ai_decisions:[]};
else if(p.includes('/audit'))x={records:[]};
await route.fulfill({contentType:'application/json',body:JSON.stringify(x)});});
await page.goto(base);await page.getByRole('button',{name:'전략 스튜디오',exact:true}).click();
const studio=page.locator('.legacy-strategy-workspace:visible');
await studio.locator('textarea.source-editor').fill('RSI 30 이하 LONG 진입. RSI 55 이상 청산. 손절 1%, 익절 2%. 횡보장에서 사용.');
await studio.getByRole('button',{name:'AI 분석 및 전략 초안 만들기',exact:true}).click();await studio.locator('.strategy-beginner-explanation').waitFor();
result.layout=[];
for(const [width,height] of [[1600,1000],[1280,800]]){
await page.setViewportSize({width,height});await studio.locator('.source-ingestor').scrollIntoViewIfNeeded();
await page.screenshot({path:out+'/studio-'+width+'.png'});
const sizes=await studio.evaluate(el=>{const nodes=[...el.querySelectorAll('p,small,dt,dd,summary,button,span,em')].filter(e=>e.getClientRects().length&&e.textContent.trim());const counts={};for(const n of nodes){const z=getComputedStyle(n).fontSize;counts[z]=(counts[z]||0)+1;}const editor=el.querySelector('.source-editor').getBoundingClientRect();return {fonts:counts,smallest:nodes.filter(n=>parseFloat(getComputedStyle(n).fontSize)<=10).slice(0,6).map(n=>({text:n.textContent.slice(0,60),size:getComputedStyle(n).fontSize})),editor:{width:editor.width,height:editor.height},scrollHeight:el.scrollHeight,width:el.getBoundingClientRect().width};});
result.layout.push({width,height,...sizes});}
for (const name of ['2. 이해·보완','3. 저장 버전·검증·차트','1. 전략 입력']) { await studio.getByRole('button',{name,exact:true}).click(); }
await page.getByRole('button',{name:'주식/증권',exact:true}).click();await page.getByRole('button',{name:'전략 스튜디오',exact:true}).click();
const stock=page.locator('.legacy-strategy-workspace:visible');await stock.locator('.source-editor').fill('주식 ETF 전략 입력');await stock.getByRole('button',{name:'1. 전략 입력',exact:true}).click();
assert((await stock.locator('.source-editor').boundingBox()).height>=220);
const stockSmall=await stock.locator('p,small,span,summary,button').evaluateAll(nodes=>nodes.filter(n=>n.getClientRects().length&&n.textContent.trim()&&parseFloat(getComputedStyle(n).fontSize)<12).map(n=>n.textContent));assert.deepEqual(stockSmall,[]);
await page.screenshot({path:out+'/studio-stock.png'});result.stockLayoutPassed=true;
await page.getByRole('button',{name:'블록체인',exact:true}).click();
await page.setViewportSize({width:1600,height:1000});await page.getByRole('button',{name:'AlphaArena',exact:true}).click();await page.getByRole('button',{name:'확인',exact:true}).click();
result.modelChat=await page.locator('.arena-output').innerText();
await page.getByRole('button',{name:'전략 판단',exact:true}).click();result.decisions=await page.locator('.arena-output').innerText();
await page.getByRole('button',{name:'PAPER 점검 결과',exact:true}).click();result.positions=await page.locator('.arena-output').innerText();
await page.getByRole('button',{name:'실행·오류 기록',exact:true}).click();result.responses=await page.locator('.arena-output').innerText();
await page.screenshot({path:out+'/alpha-events.png'});
page.on('dialog',d=>d.accept());await page.getByRole('button',{name:'▶시작',exact:true}).click();await page.getByRole('button',{name:'■정지',exact:true}).waitFor();
await page.locator('.source-tab-strip').getByRole('button',{name:'UPBIT',exact:true}).click();result.arenaHiddenAfterUpbit=(await page.locator('.legacy-alpha-arena').count())===0;result.stopRequested=result.commands.some(c=>c.action==='stop');await page.locator('.arena-running-banner').waitFor();result.backgroundIndicator=true;
await page.getByRole('button',{name:'AlphaArena',exact:true}).click();await page.getByRole('button',{name:'확인',exact:true}).click();available=false;
await page.waitForFunction(()=>{const b=[...document.querySelectorAll('.arena-engine-control button')].find(b=>b.textContent.includes('정지'));return b&&!b.disabled;},{},{timeout:9000});
await page.getByText('설정 → AlphaArena에서 기능을 활성화하고 전용 DeepSeek 키를 저장·점검하세요.',{exact:false}).waitFor();
result.disabledStopWhileRunning=await page.getByRole('button',{name:'■정지',exact:true}).isDisabled();await page.screenshot({path:out+'/alpha-disabled-stop.png'});

assert.match(result.modelChat,/VISIBLE_MODEL_EXPLANATION/);
assert.match(result.decisions,/ENTER_LONG/);
assert.match(result.positions,/SIMULATED/);
assert.equal(result.disabledStopWhileRunning,false);
assert.equal(result.stopRequested,false);
await page.getByRole('button',{name:'■정지',exact:true}).click();
await page.getByRole('button',{name:'▶시작',exact:true}).waitFor();
assert(result.commands.some(c=>c.action==='stop'));
for(const row of result.layout) { assert.equal(row.smallest.length,0); assert(row.editor.height>=220); }
assert.deepEqual(result.errors,[]);
} catch(e){result.failure=String(e);process.exitCode=1;}finally{fs.writeFileSync(out+'/results.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));await browser.close();}})();
