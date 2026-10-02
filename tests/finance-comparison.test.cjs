const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('../webui/node_modules/typescript');
const src=fs.readFileSync(require('node:path').join(__dirname,'../webui/src/financeComparison.ts'),'utf8');
const code=ts.transpileModule(src,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const context={exports:{}};vm.runInNewContext(code,context);
const {loanEstimate:loan,savingEstimate:save,numeric}=context.exports;
const near=(a,b)=>assert.ok(Math.abs(a-b)<.001,`${a} != ${b}`);
test('missing, malformed, unsafe and fractional principal values are not zero',()=>{
 for(const v of ['', ' ', 'NaN','Infinity','1e7','-1','1,000','0x10','1.5','1000000000001']) assert.equal(loan(v,'12','4','0','annuity'),null,v);
 for(const m of ['','0','601','1.5']) assert.equal(loan('1000000',m,'4','0','annuity'),null);
 assert.equal(numeric('0',0,100),0);assert.equal(numeric('',0,100),null);
});
test('zero-interest equal installments and principal are valid, not divided by zero',()=>{
 for(const method of ['annuity','principal']) {const r=loan('1200000','12','0','0',method);near(r.first,100000);near(r.last,100000);near(r.interest,0);near(r.total,1200000);}
});
test('annuity amortizes principal and maintains payments',()=>{
 const r=loan('10000000','24','4','100000','annuity');near(r.first,434249.221707);near(r.first,r.last);near(r.payments.reduce((a,b)=>a+b,0),r.principal+r.interest);near(r.total,r.principal+r.interest+100000);
});
test('equal principal decreases monthly burden and bullet preserves maturity principal',()=>{
 const p=loan('1200000','12','12','0','principal');near(p.first,112000);near(p.last,101000);near(p.interest,78000);
 const b=loan('1200000','12','12','0','bullet');near(b.first,12000);near(b.last,1212000);near(b.interest,144000);
});
test('unknown fees retain interest but prevent total and cost assertions',()=>{
 const r=loan('1000','1','12','','annuity');near(r.interest,10);assert.equal(r.total,null);assert.equal(r.cost,null);
 assert.equal(loan('1000','1','12','-1','annuity'),null);assert.equal(loan('1000','1','101','0','annuity'),null);
});
test('extreme supported duration and near-zero rates remain finite',()=>{
 for(const rate of ['0.00000000000001','100']) for(const method of ['annuity','principal','bullet']) {
 const r=loan('1000000000000','600',rate,'0',method);assert.equal(r.payments.length,600);assert.ok(Number.isFinite(r.total));assert.ok(r.interest>=0);near(r.payments[0],r.first);}
});
test('deposit and monthly installment do not pay full-year interest on future deposits',()=>{
 const d=save('1200000','12','3','0','deposit'),s=save('100000','12','3','0','installment');near(d.principal,s.principal);near(d.interest,36000);near(s.interest,19500);
});
test('tax unknown, explicit zero and illustrative 15.4 percent stay distinct',()=>{
 assert.equal(save('10000000','12','3','','deposit').maturity,null);
 near(save('10000000','12','3','0','deposit').maturity,10300000);
 near(save('10000000','12','3','15.4','deposit').maturity,10253800);
 assert.equal(save('10000000','12','3','-1','deposit'),null);assert.equal(save('10000000','12','3','101','deposit'),null);
});
test('saving duration, methods and aggregate amount are bounded',()=>{
 assert.equal(save('1000000000000','2','3','0','installment'),null);assert.equal(save('100','1.5','3','0','deposit'),null);
 assert.equal(save('100','1','3','0','unsupported'),null);assert.equal(loan('100','1','3','0','unsupported'),null);
});
