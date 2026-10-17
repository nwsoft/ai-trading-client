const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../webui/node_modules/typescript');
const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../webui/src/components/MaintenanceBatchPanel.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
function fixture(states,confirm=true){
 let index=0,effect;const timers=new Map(),calls=[],prompts=[];
 const context={exports:{},Date,Number,String,setTimeout:f=>{timers.set(1,f);return 1;},clearTimeout:k=>timers.delete(k),window:{confirm:message=>{prompts.push(message);return confirm;}},require:name=>{
  if(name==='react')return {useState:initial=>[states[index++]??initial,()=>{}],useEffect:f=>effect=f};
  if(name==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props})};
  if(name==='../venueSources')return {CRYPTO_SOURCES:['binance','okx'],STOCK_SOURCES:['kis']};
  throw Error(name);
 }};
 vm.runInNewContext(source,context);
 const client={reconciliation:async payload=>{calls.push(payload);return {state:'checked'};}};
 const tree=context.exports.MaintenanceBatchPanel({client});
 const text=n=>n==null?'':Array.isArray(n)?n.map(text).join(''):typeof n==='object'?text(n.props?.children):String(n);
 function find(n,label){if(!n)return null;if(Array.isArray(n)){for(const c of n){const r=find(c,label);if(r)return r;}return null;}if(n.type==='button'&&text(n)===label)return n;return typeof n==='object'?find(n.props?.children,label):null;}
 return {calls,prompts,timers,client,mount:()=>effect(),click:label=>{const b=find(tree,label);assert.ok(b);return b.props.onClick();}};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('resuming LIVE from a PAPER dropdown still requires LIVE confirmation',async()=>{
 const f=fixture(['paper',[],{state:'interrupted',mode:'live',items:[{source:'kis'}]},'',false],false);
 f.click('이전 선택 이어서 점검');await flush();assert.equal(f.calls.length,0);assert.equal(f.prompts.length,1);assert.match(f.prompts[0],/LIVE/);
});
test('confirmed resume uses persisted job mode and exact sources',async()=>{
 const f=fixture(['paper',['binance'],{state:'paused',mode:'live',items:[{source:'kis'}]},'',false]);
 f.click('이전 선택 이어서 점검');await flush();assert.equal(JSON.stringify(f.calls),JSON.stringify([{action:'resume',mode:'live',sources:['kis']}]));
});
test('closing panel stops polling without cancelling the background job',async()=>{
 const f=fixture(['paper',[],null,'',false]);let complete;
 f.client.reconciliation=payload=>{f.calls.push(payload);return new Promise(resolve=>complete=resolve);};
 const cleanup=f.mount();assert.equal(f.calls.length,1);cleanup();complete({state:'running'});await flush();assert.equal(f.timers.size,0);assert.equal(f.calls.length,1);assert.equal(f.calls[0],undefined);
});
