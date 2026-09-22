// Real React components; all backend/external traffic intercepted, no accounts/orders.
const {chromium} = require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = process.env.QA_BASE || 'http://127.0.0.1:4199';
const inventory = JSON.parse(fs.readFileSync('config/web_ui_feature_inventory.json'));
(async()=>{
 const browser=await chromium.launch({headless:true});
 try {
  for(const width of [1440,900]){
   const page=await browser.newPage({viewport:{width,height:1000}});
   const errors=[],writes=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.addInitScript(()=>{
    localStorage.setItem('noahai.locale.guest','ko');
    window.noahAI={bootstrap:()=>({gatewayUrl:location.origin,gatewayToken:'fixture-only',desktop:false})};
   });
   await page.route('**/*',async route=>{
    const url=new URL(route.request().url());if(url.origin!==base)return route.abort();
    const p=url.pathname;if(!p.startsWith('/api/'))return route.continue();let data={};
    if(route.request().method()!=='GET')writes.push(p);
    if(p.endsWith('/session'))data={authenticated:true,account:'fixture',user:{id:'fixture',user_grade:'premium'}};
    else if(p.endsWith('/platform'))data={release_version:'3.9.1.45'};
    else if(p.endsWith('/features'))data=inventory;
    else if(p.endsWith('/runtime/snapshot'))data={enabled_sources:['binance'],running_sources:[],paper_trading:true};
    else if(p.includes('blockchain.coin_info'))data={selected_coins:[
     {symbol:'MISSINGUSDT',overall_score:82.8,technical_score:null,volatility_score:90,volume_score:50,trend_score:100,risk_score:30},
     {symbol:'VALIDUSDT',overall_score:77.5,technical_score:80,volatility_score:70,volume_score:70,trend_score:85,risk_score:30},
    ]};
    else if(p.includes('blockchain.ai_learning'))data={learning:{status:'ok',source:'fixture/learning.sqlite3',records:[
     {id:1,symbol:'OLDUSDT',timestamp:'2026-09-22T00:00:00Z',signal:'SHORT',confidence:.5,rsi:null,macd:null,trend:null,reason:'Historical missing evidence'},
     {id:2,symbol:'NEWUSDT',timestamp:'2026-09-22T00:01:00Z',signal:'SHORT',confidence:.5,rsi:0,macd:-.1826,trend:'DOWN',reason:'Recorded fixture'},
    ]}};
    else if(p.endsWith('/logs'))data={lines:[],entries:[]};
    await route.fulfill({contentType:'application/json',body:JSON.stringify(data)});
   });
   await page.goto(base);
   await page.getByRole('button',{name:'코인 정보',exact:true}).click();
   const absent=page.locator('.legacy-coin-row').filter({hasText:'MISSINGUSDT'});
   await absent.waitFor(); assert((await absent.innerText()).includes('미산출'));
   assert((await page.locator('.legacy-coin-row').filter({hasText:'VALIDUSDT'}).innerText()).includes('80'));
   assert(await page.getByText(/기술점수 미산출: 후보 선정/).isVisible());
   await page.screenshot({path:`${process.env.AUDIT_DIR}/coin-indicators-${width}.png`});
   await page.getByRole('button',{name:'AI 학습',exact:true}).click();
   const fresh=page.locator('.legacy-learning-row').filter({hasText:'NEWUSDT'});
   await fresh.waitFor(); const cells=await fresh.locator('span').allTextContents();
   assert(cells.includes('0')); assert(cells.includes('-0.1826')); assert(cells.includes('DOWN'));
   const rowBox=await fresh.boundingBox(), tableBox=await page.locator('.legacy-learning-body').boundingBox();
   assert(rowBox && tableBox && rowBox.y >= tableBox.y && rowBox.y+rowBox.height <= tableBox.y+tableBox.height,
          'learning evidence row must not be clipped by explanatory text');
   const old=page.locator('.legacy-learning-row').filter({hasText:'OLDUSDT'});
   assert.equal((await old.innerText()).split('기록 없음').length-1,3);
   await page.screenshot({path:`${process.env.AUDIT_DIR}/learning-indicators-${width}.png`});
   assert.deepEqual(errors,[]);
   assert(!writes.some(p=>p.includes('/commands')||p.includes('/settings')));
   console.log(JSON.stringify({width,passed:true,errors,writes}));
   await page.close();
  }
 } finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
