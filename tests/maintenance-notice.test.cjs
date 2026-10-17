const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const ts=require('../webui/node_modules/typescript');
const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../webui/src/components/MaintenanceNotice.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,target:ts.ScriptTarget.ES2022}}).outputText;
function fixture(status,unavailable=false) {
 let effect,index=0,opened=0;const states=[status,unavailable],updates=[],calls=[],timers=new Map();
 const context={exports:{},Date,Number,String,Array,setTimeout:(f,delay)=>{timers.set(1,{f,delay});return 1;},clearTimeout:key=>timers.delete(key),require:name=>{
  if(name==='react')return {useState:initial=>{const i=index++;return [states[i]??initial,value=>{updates.push([i,value]);states[i]=value;}];},useEffect:f=>effect=f};
  if(name==='react/jsx-runtime')return {jsx:(type,props)=>({type,props}),jsxs:(type,props)=>({type,props}),Fragment:'fragment'};
  throw Error(name);
 }};
 vm.runInNewContext(source,context);
 const client={reconciliation:async(...args)=>{calls.push(args);return {state:'checked',mode:'paper',items:[]};}};
 const render=()=>{index=0;return context.exports.MaintenanceNotice({client,onOpen:()=>opened++});};
 const text=n=>n==null?'':Array.isArray(n)?n.map(text).join(''):typeof n==='object'?text(n.props?.children):String(n);
 function button(n){if(!n)return null;if(Array.isArray(n))return n.map(button).find(Boolean);return n.type==='button'?n:typeof n==='object'?button(n.props?.children):null;}
 return {client,calls,updates,timers,render,text,mount:()=>effect(),open:tree=>button(tree).props.onClick(),opened:()=>opened};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));
test('global notice shows progress and navigates to results without mutation',()=>{
 const f=fixture({state:'running',mode:'paper',items:[{state:'checked'},{state:'running'}]});const tree=f.render();
 assert.match(f.text(tree),/백그라운드 대조 중.*완료 1\/2/);f.open(tree);assert.equal(f.opened(),1);assert.equal(f.calls.length,0);
});
test('completed result persists with as-of time and safe engine semantics',()=>{
 const f=fixture({state:'checked',mode:'paper',updated_at:1792200000,items:[{state:'checked'}]});const text=f.text(f.render());
 assert.match(text,/대조 완료.*완료 1\/1.*마지막 기록/);assert.match(text,/거래를 새로 시작하지/);assert.match(text,/이미 실행 중인 엔진/);
});
test('partial failures and interrupted jobs remain visible',()=>{
 for(const state of ['needs_evidence','interrupted','paused','status_unavailable']) {
  const f=fixture({state,items:[{state:'needs_evidence'}]});assert.ok(f.render());assert.match(f.text(f.render()),/확인 필요 1개/);
 }
});
test('poll failure never displays a stale success as current',async()=>{
 const f=fixture({state:'checked',items:[]});f.render();f.client.reconciliation=async()=>{throw Error('offline');};const cleanup=f.mount();await flush();
 assert.match(f.text(f.render()),/대조 상태를 확인하지 못했습니다/);assert.doesNotMatch(f.text(f.render()),/대조 완료/);assert.equal(f.timers.get(1).delay,5000);cleanup();
});
test('unmount/account switch stops polling and discards old account reply',async()=>{
 const f=fixture({state:'running'});f.render();let resolve;f.client.reconciliation=async(...args)=>{f.calls.push(args);return new Promise(r=>resolve=r);};const cleanup=f.mount();cleanup();resolve({state:'checked'});await flush();assert.equal(f.updates.length,0);assert.equal(f.timers.size,0);assert.deepEqual(f.calls,[[]]);
});
test('idle result is hidden; a later read-only result becomes visible',async()=>{
 const f=fixture({state:'idle'});assert.equal(f.render(),null);const cleanup=f.mount();await flush();assert.match(f.text(f.render()),/대조 완료/);assert.deepEqual(f.calls,[[]]);cleanup();assert.equal(f.timers.size,0);
});
