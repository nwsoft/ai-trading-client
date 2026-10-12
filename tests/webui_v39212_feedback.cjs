// Render the built app with isolated synthetic API data. No accounts or orders.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const out=path.resolve(process.env.NOAHAI_QA_OUTPUT||path.join(root,'reports/v39211-v39212-feedback-20261012/ui-feedback'));fs.mkdirSync(out,{recursive:true});
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
const fixture=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/companion_usability.json')));
const wealth=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/wealth_tax.json')));
let mode='empty',enabledSources=inventory.services.flatMap(s=>s.sources);
function contrast(a,b){const lum=s=>{const c=s.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4);return c[0]*.2126+c[1]*.7152+c[2]*.0722;};const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
(async()=>{const browser=await chromium.launch({headless:true,channel:'chrome'});const page=await browser.newPage({viewport:{width:1492,height:930},timezoneId:'Asia/Seoul',locale:'ko-KR'});const errors=[],requests=[],checks=[],layouts=[];
page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());page.setDefaultTimeout(10000);
await page.addInitScript(()=>window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})});
await page.route('**/*',async route=>{const request=route.request(),url=new URL(request.url()),ep=url.pathname,body=request.method()==='GET'?null:request.postDataJSON();
if(!ep.startsWith('/api/')){const file=path.join(dist,ep==='/'?'index.html':ep);if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png'})[path.extname(file)]||'application/octet-stream'});return route.abort();}
requests.push({ep,method:request.method(),body});let payload={};
if(ep.endsWith('/platform'))payload={release_version:'3.9.2.11',release_label:'IA fixture'};
else if(ep.endsWith('/session'))payload={authenticated:true,account:'ia-fixture',user:{id:'ia-fixture',user_grade:'premium'}};
else if(ep.endsWith('/features'))payload=inventory;
else if(ep.endsWith('/display-preferences'))payload={saved:false,locale:'ko'};
else if(ep.endsWith('/runtime/snapshot'))payload={enabled_sources:enabledSources,running_sources:[],selected_sources:{blockchain:'binance',stock:'kis'},credential_status:{},paper_trading:true};
else if(ep==='/api/v1/audit/export')payload={records:[{event:'strategy.review',at:'2026-10-11T06:56:06.230482+00:00'}]};
else if(ep.endsWith('/companion/allocation'))payload=fixture.allocation;
else if(ep.endsWith('/settings'))payload={fields:[],revision:'fixture'};
else if(ep.endsWith('/companion/briefing'))payload=fixture.briefs[mode];
else if(ep.endsWith('/life-finance/tax'))payload=wealth.tax_response;
else if(ep.endsWith('/companion/query'))payload=wealth.queries[body.question]||(body.question==='연결 화면 확인'?{answer:'관련 화면으로 이어갑니다.',actions:[{id:'trading',label:'코인 거래'},{id:'stock',label:'증권 거래'},{id:'portfolio',label:'통합 자산'},{id:'life',label:'생활 금융'},{id:'market',label:'시장 분석'}]}:(fixture.queries[body.question]||fixture.queries['okx 왜 거래가 없지?']));
else if(ep.endsWith('/companion/experiments'))payload=fixture.versions;
else if(ep.includes('product-intelligence'))payload=fixture.catalog;
else if(ep==='/api/v1/life-finance')payload={summary:{cash_flow:{},goals:{}},transactions:[],goals:[],alerts:[],dashboard:{}};
else if(ep==='/api/v1/life-finance/ledger')payload={rows:[],total:0,offset:0};
else if(ep==='/api/v1/life-finance/analysis')payload={alerts:[],analysis:{},chart:{},cash_flow:{},monthly:[]};
else if(ep.endsWith('/life-finance/insurance'))payload=body?.action==='finance_plan'?{plans:[],reviews:[]}:body?.action==='finance_handoff'?{requests:[],recipients:[]}:{state:'locked',policies:[]};
else if(ep.includes('/portfolio/analysis'))payload={allocation_by_currency:{},performance_by_currency:{},positions:[],recent_closed_trades:[],account_status:{}};
else if(ep.includes('/workspaces/'))payload={source:url.searchParams.get('source'),trading:{execution_mode:'paper'},logs:[],statistics:[],ai_decisions:[],ai_analysis:[],risk:[],paper_positions:[],scenario:{available_currencies:[],policy:{},scopes:{all:{sample_count:0,scenarios:[]},stock:{sample_count:0,scenarios:[]},crypto:{sample_count:0,scenarios:[]}}}};
else if(ep.endsWith('/strategies'))payload={strategies:[],min_paper_trades:3,hub_available:false};
else if(ep.includes('/logs'))payload={lines:[],entries:[],sources:[],categories:[],levels:[]};
await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
});
const serviceNav=()=>page.getByRole('navigation',{name:'주요 서비스',exact:true});const dialog=()=>page.getByRole('dialog',{name:'내 금융비서',exact:true});const trigger=()=>page.getByRole('button',{name:'내 금융비서',exact:true});
async function ask(q){await dialog().getByLabel('무엇을 확인할까요?').fill(q);await Promise.all([page.waitForResponse(r=>r.url().endsWith('/companion/query')),dialog().getByRole('button',{name:'질문 확인',exact:true}).click()]);await dialog().locator('.companion-answer').waitFor();}
try{
await page.goto('http://127.0.0.1:4219');await serviceNav().waitFor();
const blockedNetwork=[];page.on('request',r=>{if(/\/(assistant\/ask|companion\/query)$/.test(new URL(r.url()).pathname))blockedNetwork.push(r.url());});
await page.route('**/api/v1/assistant/ask',route=>route.abort());await page.route('**/api/v1/companion/query',route=>route.abort());
const question='기관을 정지하고 운용 요약에서 보유·예약을 확인한 뒤 과거 기록을 보존하는 새 PAPER 평가를 준비하세요. 라는게 뭐야 무슨소리야?';
await trigger().click();await dialog().getByLabel('무엇을 확인할까요?').fill(question);await dialog().getByRole('button',{name:'질문 확인',exact:true}).click();
await dialog().locator('.companion-answer').waitFor();assert.match(await dialog().locator('.companion-answer').innerText(),/전략을 삭제하지 마세요/);assert.match(await dialog().locator('.companion-answer').innerText(),/현재 계정 상태는 연결 후 확인/);checks.push('companion PAPER help is immediate without server query');
await dialog().getByRole('button',{name:'금융비서 닫기',exact:true}).click();await page.locator('.feature-tab-strip').getByRole('button',{name:'AI 어시스턴트',exact:true}).click();
const input=page.locator('.legacy-chat-input input');await input.fill(question);await page.getByRole('button',{name:'전송',exact:true}).click();
const message=page.locator('.legacy-chat-message.assistant').last();await message.getByText(/내장 사용법 안내/).waitFor();assert.match(await message.innerText(),/검증 OFF/);assert.match(await message.innerText(),/새 검증 1개/);assert.match(await message.innerText(),/거래 시작/);checks.push('general assistant explains all OFF versus venue stop and new validation wallet sharing');
assert.equal(await message.getByRole('button',{name:'이 답변을 전략 스튜디오 검토 영역으로 보내기',exact:true}).count(),0);assert(await page.getByRole('button',{name:'거래소 운용 화면 열기',exact:true}).isVisible());checks.push('usage guide is not offered as strategy and exposes owning venue destination');const nextButton=page.getByRole('button',{name:'거래소 운용 화면 열기',exact:true});const colors=await nextButton.evaluate(e=>({fg:getComputedStyle(e).color,bg:getComputedStyle(e).backgroundColor,width:e.getBoundingClientRect().width}));assert(contrast(colors.fg,colors.bg)>=4.5);assert(colors.width<400);checks.push('recovery destination uses readable themed button without full-width gray fallback');
await page.getByRole('button',{name:'심층분석',exact:true}).click();await input.fill('과거 PAPER 결제통화 근거 누락');await page.getByRole('button',{name:'전송',exact:true}).click();await page.locator('.legacy-chat-message.assistant').last().getByText(/내장 사용법 안내/).waitFor();checks.push('deep mode cannot turn this shipped help question into a provider dependency');
assert.deepEqual(blockedNetwork,[]);assert(!requests.some(r=>r.ep.endsWith('/assistant/ask')||r.ep.endsWith('/companion/query')));assert(!requests.some(r=>/trading\/control|orders|maintenance\/paper-session/.test(r.ep)));assert.deepEqual(errors,[]);checks.push('no assistant network request, provider, reset, order, or browser error');
await page.screenshot({path:path.join(out,'paper-help.png')});fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:checks.length,checks,errors,requests},null,2));console.log(JSON.stringify({passed:checks.length,errors}));
}catch(e){await page.screenshot({path:path.join(out,'failure.png')});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:String(e),errors,requests},null,2));throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
