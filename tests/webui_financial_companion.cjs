// Exercise shipped React bundle; synthetic API bodies come from actual Python calculators.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dist=path.join(root,'webui/dist'),out=path.resolve(process.env.NOAHAI_QA_OUTPUT||path.join(root,'reports/v39211-companion-usability-20261011/functional-ui'));
const fixture=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/companion_functional.json')));
const inventory=JSON.parse(fs.readFileSync(path.join(root,'config/web_ui_feature_inventory.json')));
(async()=>{
 fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1440,height:980}});
 const errors=[],requests=[],checks=[];let incompatible=false,allocationError=false,slowQuery=false,releaseSlow=null;
 page.setDefaultTimeout(10000);
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',dialog=>dialog.accept());
 await page.addInitScript(()=>{
  window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture',desktop:false})};
  window.SpeechRecognition=class {start(){this.onstart?.();this.onresult?.({results:[[{transcript:window.__companionTranscript||'대출 120만원 기간 12개월'}]]});this.onend?.();}abort(){}stop(){}};
 });
 await page.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url()),ep=url.pathname;
  if(!ep.startsWith('/api/')){
   const file=path.join(dist,ep==='/'?'index.html':ep);
   if(fs.existsSync(file)&&fs.statSync(file).isFile())return route.fulfill({body:fs.readFileSync(file),contentType:({'.js':'text/javascript','.css':'text/css','.html':'text/html','.json':'application/json','.png':'image/png'})[path.extname(file)]||'application/octet-stream'});
   return route.abort();
  }
  const body=request.method()==='GET'?null:request.postDataJSON();requests.push({ep,method:request.method(),body});let payload={};
  if(ep.endsWith('/platform'))payload={release_version:'3.9.2.11',release_label:'v3.9.2.11 QA'};
  else if(ep.endsWith('/session'))payload={authenticated:true,account:'companion-fixture',user:{id:'fixture',user_grade:'premium'}};
  else if(ep.endsWith('/features'))payload=inventory;
  else if(ep.endsWith('/runtime/snapshot'))payload={enabled_sources:['binance','okx'],running_sources:[],selected_sources:{blockchain:'binance',stock:'kiwoom'},credential_status:{},paper_trading:true};
  else if(ep.endsWith('/settings'))payload={fields:[{path:'assistant_voice',value:{enabled:true,auto_tts:false,lang:'ko-KR',rate:180}}],revision:'fixture'};
  else if(ep.endsWith('/companion/briefing'))payload=fixture.brief;
  else if(ep.endsWith('/companion/query')){
   if(slowQuery)await new Promise(resolve=>releaseSlow=resolve);
   payload=fixture.queries[body.question]||fixture.queries['okx 왜 거래가 없지?'];
  }
  else if(ep.endsWith('/companion/allocation')){
   if(allocationError)return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({detail:'allocation_weights_must_sum_100'})});
   payload=fixture.allocation;
  }
  else if(ep.endsWith('/companion/experiments'))payload=fixture.versions;
  else if(ep.endsWith('/companion/experiment-compare'))payload=incompatible?fixture.incompatible:fixture.experiment;
  else if(ep.includes('product-intelligence'))payload=!body?fixture.catalog:body.action==='dialogue'?fixture.dialogue:fixture.comparison;
  else if(ep.endsWith('/life-finance/insurance')&&body?.action==='finance_handoff'&&body?.payload?.operation==='recipients')payload={recipients:[]};
  else if(ep.endsWith('/life-finance/insurance')&&body?.action==='unlock')payload={state:'unlocked',policies:[]};
  else if(ep.endsWith('/life-finance/insurance')&&body?.action==='finance_plan')payload={plans:[],reviews:[]};
  else if(ep.endsWith('/life-finance/insurance')&&body?.action==='finance_profile')payload={profile:null};
  else if(ep.endsWith('/life-finance/insurance')&&body?.action==='finance_handoff')payload={requests:[]};
  else if(ep.endsWith('/life-finance/insurance'))payload={state:'unlocked'};
  else if(ep.includes('/workspaces/'))payload={source:'binance',trading:{},logs:[],statistics:[],ai_decisions:[],paper_positions:[]};
  else if(ep.endsWith('/strategies'))payload={strategies:[],min_paper_trades:3,hub_available:false};
  else if(ep.includes('/logs'))payload={lines:[]};
  await route.fulfill({contentType:'application/json',body:JSON.stringify(payload)});
 });
 const dialog=()=>page.getByRole('dialog',{name:'내 금융비서'});
 const queryCount=()=>requests.filter(r=>r.ep.endsWith('/companion/query')).length;
 async function ask(q){await dialog().getByLabel('무엇을 확인할까요?').fill(q);await Promise.all([page.waitForResponse(r=>r.url().endsWith('/companion/query')),dialog().getByRole('button',{name:'질문 확인',exact:true}).click()]);await dialog().locator('.companion-answer').waitFor();}
 async function capture(name){await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});}
 try{
  await page.goto('http://127.0.0.1:4219');
  await page.getByRole('button',{name:'내 금융비서',exact:true}).click();
  await dialog().getByText(/확인하지 못한 영역: 상품 자료/).waitFor();
  await dialog().locator('.companion-data-guide > summary').click();
  assert.match(await dialog().innerText(),/탐색 자료 미확인개/);
  await dialog().locator('.companion-data-guide > summary').click();
  assert.equal(queryCount(),0);checks.push('opening only reads local evidence; unavailable catalog is unknown');
  await ask("코인과 주식에 시장국면 인식이 좀 다를까요? 주식의 경우 시장국면이 빠르게 바뀌는거 같은데 코인은 보통 일반 국면이더라고요. 국면 확정에 로직적 다른점이 있는지 궁금합니다");
  assert.match(await dialog().locator('.companion-answer').innerText(),/300초/);
  assert.match(await dialog().locator('.companion-answer').innerText(),/005930/);
  assert.equal(await dialog().locator('.companion-answer button').count(),2);
  await page.setViewportSize({width:1080,height:850});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const regimeLayout=await dialog().evaluate(el=>({dialogs:document.querySelectorAll('[role=dialog]').length,headers:[...el.querySelectorAll('h2')].map(h=>h.textContent),box:el.getBoundingClientRect().toJSON(),body:{height:el.querySelector('.companion-body').clientHeight,scrollHeight:el.querySelector('.companion-body').scrollHeight}}));
  assert.equal(regimeLayout.dialogs,1);assert.equal(regimeLayout.headers.length,1);
  fs.writeFileSync(path.join(out,'regime-layout.json'),JSON.stringify(regimeLayout,null,2)+'\n');
  await capture('regime-guide');
  await dialog().screenshot({path:path.join(out,'regime-dialog.png'),animations:'disabled'});
  await dialog().getByRole('button',{name:'증권 거래 현황',exact:true}).scrollIntoViewIfNeeded();
  await capture('regime-guide-actions');
  checks.push('real current regime guide renders with both venue links at 1080px');
  await page.setViewportSize({width:1440,height:980});
  await ask('okx 왜 거래가 없지?');
  assert.match(await dialog().locator('.companion-answer').innerText(),/OKX · PAPER.*목록 조회 실패/);
  assert.match(await dialog().locator('.companion-answer').innerText(),/0.65 \/ 필요 0.7/);
  checks.push('venue PAPER cause measured threshold and next action');await capture('diagnosis');
  await ask('월 부담을 줄여줘');
  assert.equal(await dialog().locator('.companion-answer button').count(),3);
  checks.push('ambiguous burden asks purpose with three review paths');
  const beforeVoice=queryCount();await dialog().getByRole('button',{name:'음성으로 질문',exact:true}).click();
  await page.waitForTimeout(30);assert.equal(await dialog().getByLabel('무엇을 확인할까요?').inputValue(),'대출 120만원 기간 12개월');assert.equal(queryCount(),beforeVoice);
  assert.match(await dialog().innerText(),/인식한 금액·기간을 확인/);checks.push('voice fills reviewable input without query or commands');
  await ask('대출 120만원 기간 12개월');
  await voiceTask('비교 화면 열어줘');assert.equal(await dialog().locator('.product-intelligence').count(),0);await dialog().getByRole('button',{name:'명령 확인 · 질문 조건으로 비교 화면 열기',exact:true}).click();checks.push('voice navigation reviews finance destination before opening');
  await dialog().getByRole('heading',{name:'내 상황으로 비교하고 다음 단계 정하기'}).waitFor();
  const form=dialog().locator('.product-intelligence');
  assert.equal(await form.getByLabel('조건 변경 질문').inputValue(),'대출 120만원 기간 12개월');
  assert.equal(Number(await form.getByLabel('빌릴 금액', {exact:true}).inputValue()),1200000);
  checks.push('explicit amount period and original question handed to existing workspace');
  async function voiceTask(text){await page.evaluate(value=>window.__companionTranscript=value,text);await dialog().getByRole('button',{name:/^음성으로 (업무 이어가기|질문)$/}).click();await dialog().getByRole('button',{name:/명령 확인 ·/}).waitFor();}
  const beforeRevision=requests.filter(r=>r.ep.includes('product-intelligence')&&r.method==='POST').length;
  await voiceTask('기간 24개월로');assert.equal(requests.filter(r=>r.ep.includes('product-intelligence')&&r.method==='POST').length,beforeRevision);
  await dialog().getByRole('button',{name:'명령 확인 · 조건 수정·재계산',exact:true}).click();await page.waitForTimeout(100);assert.equal(await form.getByLabel('기간(개월)',{exact:true}).inputValue(),'24');checks.push('voice condition revision waits for review then uses existing calculator');
  await voiceTask('현재 계획 저장해줘');await dialog().getByRole('button',{name:'명령 확인 · 현재 계획 암호화 저장',exact:true}).click();await form.getByText(/계획을 저장하려면 먼저 암호화 보관함/).waitFor();
  assert.equal(requests.filter(r=>r.body?.action==='finance_plan'&&r.body?.payload?.operation==='save').length,0);checks.push('voice save cannot bypass locked encrypted vault');
  await page.evaluate(()=>window.__companionTranscript='계획 저장하지마');await dialog().getByRole('button',{name:/^음성으로 (업무 이어가기|질문)$/}).click();await dialog().getByText(/음성 명령을 취소했습니다/).waitFor();assert.equal(await dialog().getByRole('button',{name:/명령 확인 ·/}).count(),0);checks.push('negative voice instruction cancels pending action without save');
  await form.getByText('계획 저장·다시 보기 · 암호화 보관함',{exact:true}).click();await form.getByLabel('보관함 비밀번호').fill('synthetic-only-password');await form.getByRole('button',{name:'보관함 열기',exact:true}).click();await form.getByRole('button',{name:'잠그기',exact:true}).waitFor();
  await voiceTask('현재 계획 저장해줘');assert.equal(requests.filter(r=>r.body?.action==='finance_plan'&&r.body?.payload?.operation==='save').length,0);
  await dialog().getByRole('button',{name:'명령 확인 · 현재 계획 암호화 저장',exact:true}).click();await page.waitForTimeout(100);const saves=requests.filter(r=>r.body?.action==='finance_plan'&&r.body?.payload?.operation==='save');assert.equal(saves.length,1);assert.equal(Number(saves[0].body.payload.scenario.profile.months),24);checks.push('reviewed voice save uses current scenario and existing encrypted save API once');
  await form.getByLabel('조건 변경 질문').fill('기간 24개월로');
  await form.getByRole('button',{name:'조건 반영·재계산',exact:true}).click();
  await page.waitForTimeout(100);assert.equal(await form.getByLabel('기간(개월)',{exact:true}).inputValue(),'24');checks.push('existing deterministic dialogue recalculation connected');
  await dialog().getByRole('button',{name:'질문·내 상태',exact:true}).click();
  await dialog().getByRole('button',{name:'진행 중인 비교',exact:true}).click();
  assert.equal(await form.getByLabel('조건 변경 질문').inputValue(),'기간 24개월로');checks.push('navigation retains unfinished comparison');
  await voiceTask('배분 미리보기 열어줘');await dialog().getByRole('button',{name:'명령 확인 · 배분 미리보기 열기',exact:true}).click();checks.push('voice switches to allocation preview after explicit review');
  for(const [i,symbol,before,after] of [[1,'A','80','50'],[2,'B','20','50']]){await dialog().getByLabel(`종목 ${i}`,{exact:true}).fill(symbol);await dialog().getByLabel(`현재 비중 ${i}`,{exact:true}).fill(before);await dialog().getByLabel(`바꿀 비중 ${i}`,{exact:true}).fill(after);}
  await dialog().getByRole('button',{name:'가정 비교',exact:true}).click();
  await dialog().getByText(/계산 전 · 총 가치\/비용 근거 미입력/).waitFor();
  assert.match(await dialog().locator('.companion-preview').innerText(),/60%/);checks.push('allocation shows unknown cost and actual weight movement');await capture('allocation');
  allocationError=true;await dialog().getByRole('button',{name:'가정 비교',exact:true}).click();
  await dialog().getByRole('alert').filter({hasText:'각각 100%'}).waitFor();
  assert.equal(await dialog().locator('.companion-preview').count(),0);checks.push('failed allocation clears old result');
  await dialog().getByRole('button',{name:'저장된 전략 비교',exact:true}).click();
  await dialog().getByLabel('원본',{exact:true}).selectOption('0');await dialog().getByLabel('후보',{exact:true}).selectOption('1');
  await dialog().getByRole('button',{name:'저장 결과 대조',exact:true}).click();
  await dialog().getByText('재생 순손익 %',{exact:true}).waitFor();
  assert.match(await dialog().locator('.companion-preview').innerText(),/미기록/);checks.push('same replay input metrics compare and unknown drawdown remains unknown');await capture('experiment');
  incompatible=true;await Promise.all([page.waitForResponse(r=>r.url().endsWith('/experiment-compare')),dialog().getByRole('button',{name:'저장 결과 대조',exact:true}).click()]);
  await dialog().getByText(/같은 입력 근거를 확인하지 못했습니다/).waitFor();
  assert.equal(await dialog().locator('.companion-preview table').count(),0);checks.push('legacy or mismatched replay hides numerical comparison');
  await dialog().getByRole('button',{name:'질문·내 상태',exact:true}).click();
  slowQuery=true;await dialog().getByLabel('무엇을 확인할까요?').fill('okx 왜 거래가 없지?');await dialog().getByRole('button',{name:'질문 확인',exact:true}).click();
  await page.waitForTimeout(60);await page.evaluate(()=>window.dispatchEvent(new Event('noah-finance-vault-locked')));releaseSlow?.();slowQuery=false;
  await page.waitForTimeout(150);assert.equal(await dialog().locator('.companion-answer').count(),0);checks.push('vault lock invalidates late private query response');
  await ask('손절 2%로 전략 비교해줘');
  await dialog().getByRole('button',{name:'전략 초안 검토',exact:true}).click();
  await page.locator('.strategy-assistant-draft').getByText('질문 검토 · 아직 전략에 적용되지 않음',{exact:true}).waitFor();
  assert.equal(await dialog().count(),0);checks.push('local strategy question opens studio review draft');await capture('strategy-draft');
  await page.getByRole('button',{name:'내 금융비서',exact:true}).click();await dialog().locator('.companion-boundary').waitFor();
  await page.setViewportSize({width:1080,height:850});assert(await dialog().evaluate(e=>e.scrollWidth<=e.clientWidth+1));checks.push('supported minimum viewport has no modal overflow');
  await page.evaluate(()=>{delete window.SpeechRecognition;delete window.webkitSpeechRecognition;});
  await dialog().getByRole('button',{name:'음성으로 질문',exact:true}).click();await dialog().getByText(/음성 인식을 지원하지 않습니다/).waitFor();checks.push('unsupported speech offers typed fallback');
  await page.evaluate(()=>window.SpeechRecognition=class {start(){this.onerror?.({error:'not-allowed'});}abort(){}});
  const countBeforeDenied=queryCount();await dialog().getByRole('button',{name:'음성으로 질문',exact:true}).click();await dialog().getByText(/마이크 권한·음성 연결을 확인하세요: not-allowed/).waitFor();assert.equal(queryCount(),countBeforeDenied);checks.push('denied microphone leaves input and sends no query');
  slowQuery=true;await dialog().getByLabel('무엇을 확인할까요?').fill('okx 왜 거래가 없지?');await dialog().getByRole('button',{name:'질문 확인',exact:true}).click();await page.waitForTimeout(60);
  await dialog().getByRole('button',{name:'금융비서 닫기',exact:true}).click();releaseSlow?.();slowQuery=false;await page.getByRole('button',{name:'내 금융비서',exact:true}).click();await dialog().locator('.companion-boundary').waitFor();await page.waitForTimeout(100);assert.equal(await dialog().locator('.companion-answer').count(),0);checks.push('closed modal late answer cannot leak into reopened session');
  assert.deepEqual(errors,[]);
  const commands=requests.filter(r=>!(r.ep==='/api/v1/life-finance/insurance'&&(r.body?.action==='unlock'||r.body?.action==='finance_plan'&&['list','save'].includes(r.body?.payload?.operation)||r.body?.action==='finance_profile'&&r.body?.payload?.operation==='get'||r.body?.action==='finance_handoff'&&r.body?.payload?.operation==='list'))&&!(r.ep==='/api/v1/life-finance/insurance'&&r.body?.action==='finance_handoff'&&JSON.stringify(r.body.payload)==='{"operation":"recipients"}')&&r.method!=='GET'&&!r.ep.startsWith('/api/v1/companion/')&&!r.ep.includes('product-intelligence'));
  assert.deepEqual(commands,[]);checks.push('no provider order approval external submission or unconfirmed save commands');
  const result={result:'PASS',renderer:JSON.parse(fs.readFileSync(path.join(dist,'ui-build.json'))),checks,errors,requests,synthetic:true,real_orders:0,real_accounts:false};
  fs.writeFileSync(path.join(out,'result.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({result:'PASS',checks}));
 }catch(error){await capture('failure');fs.writeFileSync(path.join(out,'failure-debug.json'),JSON.stringify({errors,requests},null,2));throw error;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
