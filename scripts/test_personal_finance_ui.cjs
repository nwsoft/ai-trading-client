// NODE_PATH=/tmp/<isolated dependencies>/node_modules node scripts/test_personal_finance_ui.cjs
// Vite on 4188, actual React components + Python-generated ephemeral records.
const {chromium}=require('playwright');
const {execFileSync}=require('node:child_process');
const assert=require('node:assert/strict');
const fixture=execFileSync('.venv/bin/python',['-c',`
import json,tempfile
from datetime import date
from trading.life_finance import LifeFinanceManager,TransactionType as T
from trading.tax_calculation_service import calc_financial_investment_tax
with tempfile.TemporaryDirectory() as directory:
 m=LifeFinanceManager(directory)
 for amount,kind in [(3000000,T.INCOME),(1200000,T.EXPENSE),(500000,T.TRANSFER)]:
  m.add_transaction(date.today(),amount,kind,'QA fixture')
 print(json.dumps({'summary':m.get_dashboard_summary(),'finance_review':m.get_finance_review(),'transactions':[t.to_dict() for t in m.transactions],'transaction_count':3,'goals':[],'tax':{'result':calc_financial_investment_tax()}},ensure_ascii=False))
`],{encoding:'utf8'}).trim();
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const width of [1490,1080]){
   const page=await browser.newPage({viewport:{width,height:980}});
   const errors=[];page.on('pageerror',e=>errors.push(String(e)));
   await page.route('**/qa/finance-data',route=>route.fulfill({contentType:'application/json',body:fixture}));
   await page.goto('http://127.0.0.1:4188/qa/personal-finance.html');
   await page.getByRole('heading',{name:'이번 달 내 돈 점검'}).waitFor();
   await page.getByText('내 계좌 이체 1건 · 500,000원 — 수입·소비에서 제외').waitFor();
   await page.getByLabel('예상 월 수입',{exact:true}).fill('3000000');
   await page.getByLabel('월 생활비·보험료 (대출 상환·목표 적립 제외)',{exact:true}).fill('1500000');
   await page.getByLabel('월 대출 상환액 (원금+이자)',{exact:true}).fill('500000');
   await page.getByLabel('월 목표 적립액',{exact:true}).fill('500000');
   await page.getByText('-100,000원',{exact:true}).waitFor();
   await page.getByLabel('예상 월 수입',{exact:true}).fill('');
   assert.equal(await page.getByText('입력 필요',{exact:true}).count(),2);
   await page.getByLabel('예상 월 수입',{exact:true}).fill('3000000');
   assert.equal(await page.evaluate(()=>window.financeQaCalls.length),0);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'desktop overflow');
   await page.screenshot({path:`/tmp/noah-finance-${width}.png`,fullPage:true});
   await page.getByRole('button',{name:'이 점검을 AI에게 질문',exact:true}).click();
   assert.equal(await page.evaluate(()=>window.financeQaCalls.length),0,'draft must not auto-send');
   await page.locator('.legacy-chat-input input').waitFor();
   assert.match(await page.locator('.legacy-chat-input input').inputValue(), /이번 달 등록된 생활금융/);
   assert.deepEqual(errors,[]);
   await page.goto('http://127.0.0.1:4188/qa/personal-finance.html?view=portfolio');
   await page.getByRole('heading',{name:'이번 달 내 돈 점검'}).waitFor();
   await page.getByRole('button',{name:'생활금융 기록·계획 열기'}).click();
   assert.equal(await page.evaluate(()=>window.financeQaCalls[0].kind),'open');
   await page.screenshot({path:`/tmp/noah-finance-portfolio-${width}.png`,fullPage:true});
   await page.goto('http://127.0.0.1:4188/qa/personal-finance.html?view=tax');
   await page.getByRole('combobox').first().selectOption('investment');
   assert.equal(await page.getByRole('spinbutton').count(),0);
   await page.getByRole('button',{name:'제도 안내 확인'}).click();
   await page.getByRole('heading',{name:'세액 미계산 · 폐지 제도'}).waitFor();
   await page.screenshot({path:`/tmp/noah-finance-tax-${width}.png`,fullPage:true});
   await page.close();
   console.log(`PASS actual LifeFinance/Portfolio/Tax ${width}px: local context, stress/empty inputs, no automatic save/AI, navigation, abolished tax notice`);
  }
  const page=await browser.newPage({viewport:{width:390,height:844}});
  await page.route('**/qa/finance-data',route=>route.fulfill({contentType:'application/json',body:fixture}));
  await page.goto('http://127.0.0.1:4188/qa/personal-finance.html?view=panel');
  await page.getByRole('heading',{name:'이번 달 내 돈 점검'}).waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'390px panel overflow');
  await page.screenshot({path:'/tmp/noah-finance-panel-390.png',fullPage:true});
  console.log('PASS shared finance panel at 390px');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1)});
