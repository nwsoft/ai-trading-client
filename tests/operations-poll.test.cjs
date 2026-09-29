const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), vm = require('node:vm'), path = require('node:path');
const ts = require('../webui/node_modules/typescript');

function fixture() {
  const timers=new Map(), delays=[], listeners=new Set(); let next=0;
  const document={hidden:false,addEventListener:(_,f)=>listeners.add(f),removeEventListener:(_,f)=>listeners.delete(f)};
  const context={exports:{},document,window:{setTimeout:(f,ms)=>{delays.push(ms);timers.set(++next,f);return next;},clearTimeout:id=>timers.delete(id)}};
  const source=fs.readFileSync(path.join(__dirname,'../webui/src/sequentialPoll.ts'),'utf8');
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
  return {poll:context.exports.startSequentialPoll, timers, delays, document, listeners,
    tick:()=>{const entry=timers.entries().next().value;assert.ok(entry);timers.delete(entry[0]);entry[1]();}};
}
const flush=()=>new Promise(resolve=>setImmediate(resolve));

test('one in-flight request, hidden pause, visibility resumes once, cleanup',async()=>{
  const f=fixture();let calls=0,done;
  f.document.hidden=true;
  const stop=f.poll(()=>{calls++;return new Promise(resolve=>done=resolve);},1000,{pauseWhenHidden:true,backoff:true});
  assert.equal(calls,0);
  f.document.hidden=false;f.listeners.forEach(fn=>fn());
  assert.equal(calls,1);
  f.listeners.forEach(fn=>fn());assert.equal(calls,1);
  done();await flush();assert.equal(f.timers.size,1);
  f.document.hidden=true;f.tick();assert.equal(calls,1);
  stop();assert.equal(f.timers.size,0);assert.equal(f.listeners.size,0);
});

test('failure backoff 5/10/20/30s then resets, without unhandled rejections',async()=>{
  const f=fixture();let fail=true;
  const stop=f.poll(async()=>{if(fail) throw Error('fixture');},1000,{backoff:true});
  await flush();
  for(let i=0;i<3;i++){f.tick();await flush();}
  assert.deepEqual(f.delays,[5000,10000,20000,30000]);
  fail=false;f.tick();await flush();assert.equal(f.delays.at(-1),1000);
  stop();
});

test('unmount during delayed response cannot restart polling',async()=>{
  const f=fixture();let done;
  const stop=f.poll(()=>new Promise(resolve=>done=resolve),1000,{pauseWhenHidden:true});
  stop();done();await flush();assert.equal(f.timers.size,0);
});
