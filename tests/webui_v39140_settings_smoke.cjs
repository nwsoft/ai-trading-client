// Fixture-only: every API is intercepted; no provider, order or message is sent.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.QA_BASE || 'http://127.0.0.1:4199';
const inventory = JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
const field = (path, value, section='general') => ({path, value, section, group:section, label:path, kind:typeof value==='boolean'?'boolean':'text', presentation:'primary', risk:'low'});
const snapshot = {revision:'fixture-1',schema_version:'1',account_scope:'fixture',save_receipt:{verified:true},fields:[
  field('paper_trading',true),field('ai_provider','openai','ai_engine'),
  field('ai_provider_profiles.analyst.provider','openai','ai_engine'),field('ai_provider_profiles.analyst.model','gpt-test','ai_engine'),
  field('ai_data_routing.public_openai_model','gpt-test','ai_engine'),field('alpha_arena.enabled',true,'alpha'),field('alpha_arena.engine','deepseek-v4-flash','alpha'),
],credential_status:{'ai:openai':true,'ai:openai_shared':true,'alpha:deepseek':true,binance:true,upbit:true,'notification:discord':true},
credential_field_status:{openai:{api_key:true},openai_shared:{api_key:true},'alpha:deepseek':{api_key:true},binance:{api_key:true,secret_key:true},upbit:{api_key:true,secret_key:true}},
model_catalogs:{openai:{chat_text:['gpt-test']}},model_catalog_details:{openai:[{model:'gpt-test',capabilities:['chat_text'],strength:'fixture',limitation:'fixture'}]}};
(async()=>{
 const browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1600,height:1000}});page.setDefaultTimeout(10000);
 const errors=[],probes=[];let notificationCalls=0;
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 await page.addInitScript(()=>{window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'isolated-settings-fixture',desktop:false})};});
 await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.origin!==base)return route.abort();const p=url.pathname;if(!p.startsWith('/api/'))return route.continue();let data={};
   if(p.endsWith('/platform'))data={release_version:'3.9.1.40'};
   else if(p.endsWith('/session'))data={authenticated:true,account:'fixture',user:{id:'fixture',user_grade:'premium'}};
   else if(p.endsWith('/features'))data=inventory;
   else if(p.endsWith('/runtime/snapshot'))data={enabled_sources:['binance','upbit'],running_sources:[],paper_trading:true,selected_sources:{blockchain:'binance'}};
   else if(p.endsWith('/settings')||p.endsWith('/settings/credentials'))data=snapshot;
   else if(p.endsWith('/settings/diagnostics'))data={trading:{paper_trading:true}};
   else if(p.endsWith('/settings/ai-provider-check')){const b=route.request().postDataJSON();probes.push(b);const model=b.provider==='alpha:deepseek'?'deepseek-v4-flash':'gpt-test';data={model_callable:true,catalog_checked:true,models:[model],model_listed:true,requested_model:model,actual_model:model,probe_usage:{total_tokens:3},credential_scope:b.provider};}
   else if(p.endsWith('/notifications/test')){notificationCalls++;if(notificationCalls>1)return route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({detail:'fixture notification failure'})});data={ok:true,channel:'discord'};}
   else if(p.endsWith('/notifications/status'))data={};
   else if(p.includes('/accounts/refresh'))data={sources:{binance:{status:'available',balances:[]}}};
   else if(p.includes('/alpha-arena'))data={available:true,running:false,paper_trading:true,events:[]};
   else if(p.endsWith('/logs'))data={lines:[],entries:[]};
   await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
 });
 try {
   await page.goto(base);await page.getByRole('button',{name:'설정',exact:true}).click();
   const dialog=page.locator('.settings-center');await dialog.getByRole('button',{name:'AlphaArena',exact:true}).click();
   const probe=dialog.getByRole('button',{name:'선택 모델 1회 실제 호출 점검',exact:true});await probe.click();
   await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).waitFor();assert.equal(probes.at(-1).provider,'alpha:deepseek');
   await page.screenshot({path:process.env.AUDIT_DIR+'/alpha-settings-check.png'});
   await dialog.getByRole('button',{name:'AI 엔진/API',exact:true}).click();
   const provider=dialog.locator('.settings-credential-panel > select');await provider.selectOption('openai_shared');await probe.click();
   await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).waitFor();assert.equal(probes.at(-1).provider,'openai_shared');
   await provider.selectOption('openai');
   await page.waitForFunction(()=>!document.querySelector('.settings-ai-model-grid .account-ready'));
   assert.equal(await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).count(),0);
   await probe.click();await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).waitFor();
   const key=dialog.locator('.credential-input-grid input').first();await key.fill('dummy-replacement');
   assert.equal(await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).count(),0);
   assert.equal(await dialog.locator('.settings-ai-model-grid .account-ready').count(),0);
   await dialog.getByRole('button',{name:'새 값 저장',exact:true}).click();
   await key.fill('');assert.equal(await dialog.getByText('선택 모델 실제 호출 확인됨',{exact:true}).count(),0);
   await dialog.getByRole('button',{name:'거래소 API',exact:true}).click();await provider.selectOption('binance');
   await dialog.getByRole('button',{name:'저장된 키로 실제 연결 점검',exact:true}).click();await dialog.locator('.support-summary').waitFor();
   await provider.selectOption('upbit');await page.waitForFunction(()=>!document.querySelector('.support-summary'));
   await dialog.getByRole('button',{name:'알림·리포트',exact:true}).click();
   const tests=dialog.getByRole('button',{name:/테스트/});
   await tests.first().click();await dialog.getByText('최근 테스트 성공',{exact:true}).waitFor();
   await tests.first().click();await dialog.getByText('fixture notification failure',{exact:false}).waitFor();
   assert.equal(await dialog.getByText('최근 테스트 성공',{exact:true}).count(),0);
   assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true,probes,notificationCalls,errors}));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
