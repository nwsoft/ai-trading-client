const {chromium}=require(process.env.NOAHAI_QA_PLAYWRIGHT || '/tmp/noah-feedback-ui-qa/node_modules/playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});let checks=[];try{
for(const service of ['stock','crypto'])for(const profile of ['beginner','standard','advanced']){
 const page=await browser.newPage({viewport:{width:1440,height:1100}});page.on('dialog',d=>d.accept());
 const url=`http://127.0.0.1:5193/qa/strategy-feedback.html?service=${service}&profile=${profile}`;
 for(const days of [1,3,7]){
  await page.goto(url+'&control_state=approved');
  await page.getByRole('combobox',{name:/PAPER 시험 기간/}).selectOption(String(days));
  await page.getByRole('button',{name:'모의 운용 시작',exact:true}).click();
  await page.getByRole('button',{name:'모의 운용 일시정지',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.__qaStrategyActions.at(-1).trial_days),days);
  assert.equal(await page.getByRole('combobox',{name:/PAPER 시험 기간/}).isDisabled(),true);
  await page.getByRole('button',{name:'모의 운용 일시정지',exact:true}).click();
  await page.getByRole('button',{name:'모의 운용 이어가기',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.__qaStrategyActions.at(-1).action),'stop_paper');
  await page.getByRole('button',{name:'모의 운용 이어가기',exact:true}).click();
  await page.getByRole('button',{name:'모의 운용 일시정지',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window.__qaStrategyActions.at(-1).trial_days),days);
  checks.push(`${service}/${profile}/${days}: saved goal, pause, resume`);
 }
 await page.goto(url+'&trial=missing');
 let text=await page.locator('body').innerText();assert.match(text,/観察|관찰 목표에 도달/);assert.match(text,/아직 기록 없음/);assert.equal(await page.getByRole('button',{name:'조건 확인 후 최종 적용',exact:true}).count(),0);
 checks.push(`${service}/${profile}: goal reached continues; missing time and risk prevent promotion`);
 await page.goto(url+'&trial=ready');
 text=await page.locator('body').innerText();assert.match(text,/1.250초/);assert.match(text,/앱 종료 시간 포함/);
 await page.getByRole('button',{name:'조건 확인 후 최종 적용',exact:true}).click();
 await page.getByRole('button',{name:'전략 적용 일시정지',exact:true}).waitFor();assert.equal(await page.evaluate(()=>window.__qaStrategyActions.at(-1).action),'activate');
 checks.push(`${service}/${profile}: measured time separate; explicit final confirmation`);
 await page.screenshot({path:path.join(__dirname,`trial-${service}-${profile}.png`),fullPage:true});await page.close();
}
fs.writeFileSync(path.join(__dirname,'trial-ui.json'),JSON.stringify({status:'PASS',count:checks.length,checks,scope:'Real React component in synthetic browser fixture; no Windows or external institution'},null,2));console.log(`${checks.length} UI checks passed`);
}finally{await browser.close();}})().catch(e=>{console.error(e.stack);process.exitCode=1;});
