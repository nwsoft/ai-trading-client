// Render built client and portal with intercepted fixture APIs; no external requests.
const { chromium } = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const portal=process.env.DALTRADING_ROOT || '/Users/playone/SynologyDrive/Works/daltrading';
const output=process.env.AUDIT_DIR || 'reports/v39141-remote';
const inventory=JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  const browser=await chromium.launch({headless:true,executablePath:process.env.QA_CHROME_EXECUTABLE});
  const errors=[],mutations=[];
  try {
    const page=await browser.newPage({viewport:{width:1600,height:1050}});
    page.on('pageerror',error=>errors.push(error.message));page.on('dialog',d=>d.accept());
    let state={enabled:false,name:'내 NoahAI PC',allow_pause:false,entry_pauses:{},last_sent:null};
    await page.addInitScript(()=>{window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture-only',desktop:false})};});
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());if(url.hostname!=='client.qa.test')return route.abort();
      const p=url.pathname;let data={};
      if(!p.startsWith('/api/')){
        const filename=p.startsWith('/assets/')?path.join('webui/dist/assets',path.basename(p)):'webui/dist/index.html';
        return route.fulfill({path:filename,contentType:filename.endsWith('.js')?'application/javascript':filename.endsWith('.css')?'text/css':'text/html'});
      }
      if(p.endsWith('/platform'))data={release_version:'3.9.1.41'};
      else if(p.endsWith('/session'))data={authenticated:true,account:'fixture',user:{id:'fixture',user_grade:'premium'}};
      else if(p.endsWith('/features'))data=inventory;
      else if(p.endsWith('/runtime/snapshot'))data={enabled_sources:['binance','kis'],running_sources:[],paper_trading:true,selected_sources:{blockchain:'binance',stock:'kis'}};
      else if(p.endsWith('/settings'))data={fields:[],revision:'fixture',credential_status:{},credential_field_status:{}};
      else if(p.endsWith('/remote/status'))data=state;
      else if(p.endsWith('/remote/configure')){const body=route.request().postDataJSON();mutations.push(body);state={...state,...body};data=state;}
      else if(p.endsWith('/logs'))data={entries:[],lines:[]};
      await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    });
    await page.goto('https://client.qa.test');
    await page.getByRole('button',{name:'설정',exact:true}).click();
    await page.locator('.settings-center').getByRole('button',{name:'알림·리포트',exact:true}).click();
    const panel=page.locator('.remote-monitor-settings');await panel.getByText('상태 공유 꺼짐',{exact:true}).waitFor();
    await panel.getByLabel('모바일에서 신규 주문 제출 일시정지 허용').check();
    await panel.getByRole('button',{name:'상태 공유에 동의하고 연결'}).click();
    await panel.getByText('상태 공유 켜짐',{exact:true}).waitFor();
    assert.equal(mutations.at(-1).allow_pause,true);
    await page.screenshot({path:output+'/pc-settings.png'});
    const mobile=await browser.newPage({viewport:{width:390,height:844}});
    mobile.on('pageerror',e=>errors.push(e.message));mobile.on('dialog',d=>d.accept());
    let online=true,paused=false,deviceName='내 Windows PC',betaEnabled=true;
    await mobile.route('**/*',async route=>{
      const url=new URL(route.request().url());if(url.hostname!=='portal.qa.test')return route.abort();
      if(url.pathname==='/remote')return route.fulfill({body:fs.readFileSync(path.join(portal,'templates/remote_dashboard.html'),'utf8').replace("{{ 'true' if enabled else 'false' }}",String(betaEnabled)),contentType:'text/html'});
      if(url.pathname==='/static/remote_dashboard.js')return route.fulfill({path:path.join(portal,'static/remote_dashboard.js'),contentType:'application/javascript'});
      let data={};
      if(url.pathname==='/remote/devices')data={csrf:'fixture',devices:[{id:'pc-test',name:deviceName,online,last_seen:Date.now()/1000,revoked:false,snapshot:{version:'3.9.1.41',capabilities:['status','pause_entries'],sources:[{source:'kiwoom',mode:'paper',running:true,entry_pause:{paused,status:paused?'paused':'enabled'}},{source:'binance',mode:'live',running:true}]}}]};
      else if(url.pathname.endsWith('/pause')){paused=true;data={status:'pending'};}
      return route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
    });
    await mobile.goto('https://portal.qa.test/remote');
    await mobile.getByRole('button',{name:'KIWOOM 신규 제출 일시정지',exact:true}).waitFor();
    assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    await mobile.screenshot({path:output+'/mobile-online.png',fullPage:true});
    await mobile.getByRole('button',{name:'KIWOOM 신규 제출 일시정지',exact:true}).click();
    await mobile.getByText('요청을 전달했습니다.',{exact:false}).waitFor();
    await mobile.getByRole('button',{name:'새로고침',exact:true}).click();
    await mobile.getByText('신규 제출 일시정지',{exact:true}).waitFor();
    online=false;await mobile.getByRole('button',{name:'새로고침',exact:true}).click();
    await mobile.getByText('오프라인 · 마지막 확인 정보',{exact:true}).waitFor();
    assert.equal(await mobile.getByRole('button',{name:'BINANCE 신규 제출 일시정지'}).count(),0);
    await mobile.screenshot({path:output+'/mobile-offline.png',fullPage:true});
    online=true;deviceName='A'.repeat(60);
    for(const width of [320,360,390,414,768,1280]) {
      await mobile.setViewportSize({width,height:844});
      await mobile.getByRole('button',{name:'새로고침',exact:true}).click();
      await mobile.getByRole('heading',{name:deviceName,exact:true}).waitFor();
      assert.equal(await mobile.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,`overflow at ${width}`);
      const sizes=await mobile.locator('button:visible').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));
      assert.ok(sizes.every(height=>height>=44),`touch size at ${width}`);
    }
    betaEnabled=false;await mobile.reload();
    await mobile.getByText('이 계정에는 원격 관리 베타가 아직 열리지 않았습니다.',{exact:false}).waitFor();
    assert.equal(await mobile.locator('#devices button').count(),0);
    assert.equal(await mobile.locator('#refresh').isVisible(),false);
    assert.deepEqual(errors,[]);
    fs.writeFileSync(output+'/results.json',JSON.stringify({errors,mutations,desktop:true,mobile:true,offline_blocks_controls:true},null,2));
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
