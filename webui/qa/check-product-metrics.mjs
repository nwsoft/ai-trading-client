import assert from 'node:assert/strict';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless:true,channel:'chrome'});
const page = await browser.newPage();
const errors=[];page.on('pageerror',e=>errors.push(e.message));
for(const width of [1440,390]) {
 await page.setViewportSize({width,height:1000});
 await page.goto('http://127.0.0.1:5196/qa/product-metrics.html');
 const enabled=page.getByRole('button',{name:'동의하고 통계 켜기'});
 await enabled.waitFor();assert.equal(await enabled.isDisabled(),true);
 const checkbox=page.getByRole('checkbox');assert.equal(await checkbox.isChecked(),false);
 await checkbox.check();await enabled.click();
 const revoke=page.getByRole('button',{name:'통계 동의 철회 · 미전송 활동 삭제'});
 await revoke.waitFor();
 await page.screenshot({path:`../../consent-enabled-${width}.png`,fullPage:true});
 await revoke.click();await enabled.waitFor();assert.equal(await enabled.isDisabled(),true);
 assert.equal(await checkbox.isChecked(),false);
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 await page.screenshot({path:`../../consent-disabled-${width}.png`,fullPage:true});
}
await browser.close();assert.deepEqual(errors,[]);
console.log(JSON.stringify({viewports:[1440,390],default_opt_in:false,explicit_consent:true,withdrawal:true,no_overflow:true,page_errors:errors}));
