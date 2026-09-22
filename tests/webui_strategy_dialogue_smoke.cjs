// Real React routing + review controls; external AI/API responses are fixtures.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT||'playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
const base=process.env.QA_BASE||'http://127.0.0.1:4199';
const inventory=JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{for(const market of ['blockchain','stock'])for(const width of [1440,900]){
  const page=await browser.newPage({viewport:{width,height:1000}});
  const errors=[],writes=[],calls=[],analyses=[];let turn=0;
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{localStorage.setItem('noahai.locale.guest','ko');window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture-only',desktop:false})};});
  await page.route('**/*',async route=>{
   const req=route.request(),url=new URL(req.url());if(url.origin!==base)return route.abort();
   const p=url.pathname;if(!p.startsWith('/api/'))return route.continue();let data={};
   if(req.method()!=='GET')writes.push(p);
   if(p.endsWith('/session'))data={authenticated:true,account:'fixture',user:{id:'fixture',user_grade:'premium'}};
   else if(p.endsWith('/platform'))data={release_version:'3.9.1.45'};
   else if(p.endsWith('/features'))data=inventory;
   else if(p.endsWith('/settings'))data={fields:[]};
   else if(p.endsWith('/runtime/snapshot'))data={enabled_sources:['binance','kis'],running_sources:[],paper_trading:true};
   else if(p.endsWith('/assistant/ask')){
    const body=req.postDataJSON();calls.push(body);turn++;
    data={answer:turn===1?'예산은 어느 정도인가요?':'조건을 확인했습니다. 검토 초안을 전달할 수 있습니다.',
          provider_called:true,provider:'fixture',model:'not-a-live-model',strategy_consultation:{status:turn===1?'needs_clarification':'review_draft',
          understanding:{goal:'초안 만들기'},draft_text:turn===1?'':'RSI 30 이하 진입, RSI 55 이상 청산. 거래당 계좌 손실 0.5%. 검토용 초안.'}};
   }else if(p.endsWith('/strategies/source-analysis')){analyses.push(req.postDataJSON());data={status:'needs_clarification',ready_for_execution:false,missing_conditions:['거래 비용 확인'],source:{}};}
   else if(p.endsWith('/strategies'))data={strategies:[],versions:[]};
   else if(p.endsWith('/logs'))data={lines:[],entries:[]};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
  });
  await page.goto(base);
  if(market==='stock')await page.getByRole('button',{name:'주식/증권',exact:true}).click();
  await page.getByRole('button',{name:'전략 스튜디오',exact:true}).click();
  if(width===900){
   await page.locator('.source-editor:visible').fill('사용자의 기존 RSI 원문 유지');
   await page.getByRole('button',{name:'AI 어시스턴트',exact:true}).click();
   await page.getByRole('button',{name:'전략 상담 · 외부 AI',exact:true}).click();
  }else await page.getByRole('button',{name:'AI와 전략 상담',exact:true}).click();
  const input=page.locator('.legacy-chat-input input');
  await input.fill('초안 만들기. 조건은 질문해줘.');
  await page.getByRole('button',{name:'전송',exact:true}).click();
  await page.getByText('예산은 어느 정도인가요?',{exact:true}).waitFor();
  assert.equal(await page.getByRole('button',{name:'이 답변을 전략 스튜디오 검토 영역으로 보내기',exact:true}).count(),0);
  await input.fill('예산 100만원. 확인한 조건으로 만들어줘.');
  await page.getByRole('button',{name:'전송',exact:true}).click();
  const handoff=page.getByRole('button',{name:'이 답변을 전략 스튜디오 검토 영역으로 보내기',exact:true});
  await handoff.waitFor();
  assert.equal(calls[1].conversation_kind,'strategy');assert.equal(calls[1].strategy_service,market);
  assert.equal(calls[1].mode,'deep_analysis');assert.equal(calls[1].data_scope,'private');
  assert.equal(calls[1].strategy_preferences.goal,'초안 만들기');
  await page.screenshot({path:`${process.env.AUDIT_DIR}/strategy-dialogue-${market}-${width}.png`});
  await handoff.click();
  await page.getByText('AI 답변 검토 · 아직 전략에 적용되지 않음',{exact:true}).waitFor();
  assert(!writes.some(p=>p.endsWith('/source-analysis')),'handoff alone must not analyze/save');
  const analyzed=page.waitForResponse(r=>r.url().endsWith('/strategies/source-analysis'));
  await page.getByRole('button',{name:'사용자 보완 근거로 확정·재분석',exact:true}).click();
  await analyzed;
  assert.equal(analyses.length,1);
  if(width===900){
   assert.equal(analyses[0].value,'사용자의 기존 RSI 원문 유지');
   assert(analyses[0].supplemental_text.includes('RSI 30 이하'));
  }else{
   assert.equal(analyses[0].source_kind,'text');
   assert(analyses[0].value.includes('RSI 30 이하'));
   assert.equal(analyses[0].supplemental_text,'');
  }
  assert.deepEqual(errors,[]);
  assert(writes.every(p=>p.endsWith('/assistant/ask')||p.endsWith('/strategies/source-analysis')),JSON.stringify(writes));
  console.log(JSON.stringify({market,width,passed:true,calls:calls.length,writes,errors}));
  await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
