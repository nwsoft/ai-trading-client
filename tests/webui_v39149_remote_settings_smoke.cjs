// Real PC settings component; fixture client and no external network.
const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT || 'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,channel:'chrome'});
 const page=await browser.newPage({viewport:{width:1100,height:900}}),errors=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
 try {
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());if(url.hostname!=='127.0.0.1')return route.abort();
   if(url.pathname!=='/remote-settings-test')return route.continue();
   return route.fulfill({contentType:'text/html',body:`<html><body style="background:#182334;color:white"><div id="root"></div><script type="module">
import RefreshRuntime from '/@react-refresh';RefreshRuntime.injectIntoGlobalHook(window);window.$RefreshReg$=()=>{};window.$RefreshSig$=()=>type=>type;window.__vite_plugin_react_preamble_installed__=true;
</script><script type="module">
import React from '/@id/react';import ReactDOM from '/@id/react-dom/client';
import {RemoteMonitorSettings} from '/src/components/RemoteMonitorSettings.tsx';
window.fixture={state:{enabled:false,name:'QA PC',allow_pause:false,allow_control:false,share_details:false,connection_status:'disabled',entry_pauses:{}},writes:[]};
const client={remoteStatus:async()=>window.fixture.state,configureRemote:async(enabled,name,allow_pause,allow_control,share_details)=>{
const next={enabled,name,allow_pause,allow_control,share_details,connection_status:'connecting',entry_pauses:{},approved:{binance:{mode:'paper'}}};window.fixture.writes.push(next);return window.fixture.state=next;}};
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(RemoteMonitorSettings,{client}));
</script></body></html>`});
  });
  await page.goto('http://127.0.0.1:4209/remote-settings-test');
  await page.getByText('상태 공유 꺼짐',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.fixture.writes.length),0);
  await page.getByRole('checkbox',{name:/자율운행 시작·재개 허용/}).check();
  await page.getByRole('button',{name:'상태 공유에 동의하고 연결',exact:true}).click();
  await page.getByText(/첫 전송 확인 대기/).waitFor();
  const saved=await page.evaluate(()=>window.fixture.writes[0]);
  assert.equal(saved.allow_control,true);assert.equal(saved.share_details,false);
  await page.evaluate(()=>{window.fixture.state={...window.fixture.state,connection_status:'connected',last_sent:Date.now()/1000};});
  await page.getByText(/최근 전송 성공/).waitFor({timeout:20000});
  const reports=fs.mkdtempSync(path.join(os.tmpdir(),'noah-v49-remote-pc-'));
  await page.screenshot({path:path.join(reports,'settings.png')});
  assert.deepEqual(errors,[]);console.log(JSON.stringify({result:'PASS',reports,errors,fixtureSaves:1}));
 }catch(e){console.error(errors);throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
