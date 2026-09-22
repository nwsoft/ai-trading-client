// All backend and external requests intercepted. No orders/messages/accounts.
const {chromium} = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.QA_BASE || 'http://127.0.0.1:4199';
const inventory = JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
const prefix = 'notification_integrations.market_regime_modes.';
const fields = [['paper','PAPER'],['live','LIVE'],['learning','학습·관찰']].map(([mode,label])=>({
  path:prefix+mode,label:'시장국면 알림 · '+label,section:'notifications',group:'알림·리포트',
  kind:'boolean',value:true,default_value:true,presentation:'primary',risk:'low',
  help:'실행 중인 기관의 시장국면 변화 수신만 선택합니다. 분석·거래를 시작하거나 전략 조건·LIVE 위험 경고를 변경하지 않습니다.'
}));
const snapshot={revision:'fixture-1',schema_version:'1',account_scope:'fixture',fields,
  credential_status:{},credential_field_status:{},model_catalogs:{},save_receipt:{verified:true}};
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  for(const width of [1440,900]){
   const page=await browser.newPage({viewport:{width,height:1000}});
   const errors=[],saves=[];page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{
    localStorage.setItem('noahai.locale.guest','ko');
    window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture-only',desktop:false})};
   });
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
    const p=url.pathname;if(!p.startsWith('/api/'))return route.continue();let data={};
    if(p.endsWith('/session'))data={authenticated:true,account:'fixture',user:{id:'fixture',user_grade:'premium'}};
    else if(p.endsWith('/platform'))data={release_version:'3.9.1.44'};
    else if(p.endsWith('/features'))data=inventory;
    else if(p.endsWith('/runtime/snapshot'))data={enabled_sources:['binance'],running_sources:[],paper_trading:true};
    else if(p.endsWith('/settings')){
     if(route.request().method()!=='GET'){
      const b=route.request().postDataJSON();saves.push(b);
      for(const field of fields)if(Object.hasOwn(b.changes||{},field.path))field.value=b.changes[field.path];
     }
     data=snapshot;
    }
    else if(p.endsWith('/logs'))data={lines:[],entries:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   });
   await page.goto(base);await page.getByRole('button',{name:'설정',exact:true}).click();
   const dialog=page.locator('.settings-center');
   await dialog.getByRole('button',{name:'알림·리포트',exact:true}).click();
   for(const field of fields){
    const row=dialog.locator('label').filter({has:page.getByText(field.label,{exact:true})});
    assert.equal(await row.locator('input[type=checkbox]').count(),1);
    await row.scrollIntoViewIfNeeded();assert(await row.isVisible());
   }
   const paper=dialog.locator('label').filter({has:page.getByText('시장국면 알림 · PAPER',{exact:true})}).locator('input');
   await paper.setChecked(false);
   const save=dialog.getByRole('button',{name:/현재 설정 저장/});
   await save.click();await page.waitForFunction(()=>document.body.innerText.includes('저장'));
   assert(saves.some(b=>b.changes?.[prefix+'paper']===false));
   assert(saves.every(b=>Object.keys(b.changes||{}).every(k=>k.startsWith(prefix))));
   assert.deepEqual(errors,[]);
   await paper.evaluate(element=>element.scrollIntoView({block:'center'}));
   await page.screenshot({path:`${process.env.AUDIT_DIR}/regime-modes-${width}.png`});
   console.log(JSON.stringify({width,passed:true,saves,errors}));
   fields[0].value=true;await page.close();
  }
 } finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
