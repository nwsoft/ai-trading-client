// Usage: NODE_PATH=<isolated build>/node_modules node scripts/test_assistant_support_ui.cjs
// Vite QA server on 4187. Reads real guide code; no user settings or API calls.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const width of [1490,1080]){
   const page=await browser.newPage({viewport:{width,height:980}});
   const errors=[]; page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/qa/support-answer',async route=>{
    const {question}=JSON.parse(route.request().postData());
    const output=execFileSync('.venv/bin/python',['-c',
     'import json,sys; from config.assistant_support_knowledge import build_support_answer; print(json.dumps({"answer":build_support_answer(sys.argv[1]),"provider_called":False}))',question],{encoding:'utf8'});
    await route.fulfill({contentType:'application/json',body:output});
   });
   await page.goto('http://127.0.0.1:4187/qa/assistant-support.html');
   await page.getByRole('button',{name:'OKX 후보 없음',exact:true}).click();
   assert.equal(await page.evaluate(()=>window.supportQaCalls.length),0,'quick question must not auto-send');
   await page.getByRole('button',{name:'전송',exact:true}).click();
   await page.getByText('후보 선정 단계의 시작 보류입니다.',{exact:false}).waitFor();
   await page.getByRole('button',{name:'JEV 검토 현황',exact:true}).click();
   await page.getByRole('button',{name:'전송',exact:true}).click();
   await page.getByText('현재 NoahAI 실행 Provider로 통합되지 않았으며',{exact:false}).waitFor();
   assert.equal(await page.evaluate(()=>window.supportQaCalls.length),2);
   assert.deepEqual(errors,[]);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no horizontal overflow');
   await page.screenshot({path:`/tmp/noah-assistant-support-${width}.png`,fullPage:true});
   console.log(`PASS assistant actual component ${width}px: explicit submit, current OKX/JEV guide, no overflow/page errors`);
   await page.close();
  }
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
