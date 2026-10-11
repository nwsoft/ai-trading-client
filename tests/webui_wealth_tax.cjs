// Render the built app with isolated synthetic API data. No accounts or orders.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist');
const out=path.resolve(process.env.NOAHAI_QA_OUTPUT||path.join(root,'reports/v39211-wealth-audit-20261011/ui'));fs.mkdirSync(out,{recursive:true});
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
await page.goto('http://127.0.0.1:4219');await serviceNav().waitFor();await trigger().click();await dialog().locator('.companion-boundary').waitFor();
for(const q of ['ISA와 IRP 중 내게 뭐가 유리해?','매달 나가는 돈을 줄이고 절세해서 목돈을 모으고 싶어','5년 예금하면 비과세야?']){
 await ask(q);assert(await dialog().getByRole('button',{name:'절세 조건·세금 계산 확인',exact:true}).isVisible());checks.push(q+' preserves tax route and explains limits');
}
await dialog().getByRole('button',{name:'절세 조건·세금 계산 확인',exact:true}).click();await page.getByRole('heading',{name:'세금 계산 & 절세 시뮬레이터'}).waitFor();assert.equal(await dialog().count(),0);checks.push('tax action opens owning life-finance tax screen');
assert.equal(await page.getByLabel('연간 급여',{exact:true}).inputValue(),'');checks.push('salary is blank rather than a manufactured profile');
const count=()=>requests.filter(r=>r.ep.endsWith('/life-finance/tax')).length;
await page.getByRole('button',{name:'세금 계산하기',exact:true}).click();await page.getByText('연간 급여 항목을 입력하세요.',{exact:false}).waitFor();assert.equal(count(),0);checks.push('missing amount is explained without an API calculation');
await page.getByLabel('계산 유형',{exact:true}).selectOption('saving_accounts');
for(const [label,value] of [['연간 급여','50000000'],['연간 투자액','10000000'],['투자 기간(년)','3'],['예상 연 수익률(0~1)','0.1']])await page.getByLabel(label,{exact:true}).fill(value);
await page.getByRole('button',{name:'세금 계산하기',exact:true}).click();await page.getByRole('region',{name:'세금 계산 결과'}).waitFor();assert.equal(count(),1);
const result=page.getByRole('region',{name:'세금 계산 결과'});assert.match(await result.innerText(),/108,900원/);assert.match(await result.innerText(),/미확인/);assert(!/가장 유리한 절세 계좌/.test(await result.innerText()));checks.push('separate ISA tax and unknown pension tax render without a best-account claim');
const metricLabel=await result.getByText('가정 수익의 세금',{exact:true}).first().boundingBox();assert(metricLabel.width>200);checks.push('tax labels use the card width rather than narrow nested columns');
assert(!Object.hasOwn(requests.find(r=>r.ep.endsWith('/life-finance/tax')).body,'interest_income'));checks.push('only selected calculator assumptions are submitted');
await page.screenshot({path:path.join(out,'tax-comparison.png'),fullPage:true});
await result.getByText('가정 수익의 세금',{exact:true}).first().scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'tax-comparison-details.png')});
await page.getByLabel('연간 투자액',{exact:true}).fill('9000000');assert.equal(await result.count(),0);checks.push('changing input removes stale comparison');
await trigger().click();await ask('구독료와 보험료 줄여서 월30만원 더 모으고 싶어');assert.match(await dialog().locator('.companion-answer').innerText(),/반복 결제/);assert(await dialog().getByRole('button',{name:'생활금융',exact:true}).isVisible());checks.push('expense question retains recurring-expense context');
await page.screenshot({path:path.join(out,'expense-question.png')});
assert.deepEqual(errors,[]);assert(!requests.some(r=>/trading\/control|orders|strategy.*approve/.test(r.ep)));checks.push('no browser errors or trade commands');
fs.writeFileSync(path.join(out,'result.json'),JSON.stringify({passed:checks.length,checks,errors,requests},null,2));console.log(JSON.stringify({passed:checks.length,errors}));
}catch(e){await page.screenshot({path:path.join(out,'failure.png')});fs.writeFileSync(path.join(out,'failure.json'),JSON.stringify({error:String(e),errors,requests},null,2));throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
