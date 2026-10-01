const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),Module=require('node:module');
const {execFileSync}=require('node:child_process');
const ts=require(process.env.NOAHAI_QA_TYPESCRIPT||'../webui/node_modules/typescript');
const filename=require('node:path').resolve(__dirname,'../webui/src/strategyBulk.ts');
const mod=new Module(filename,module);mod._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,filename);
const {bulkDecision,bulkKey,strategyZip,EXPORT_LIMIT}=mod.exports;
const row=(extra={})=>({scope:'unified',version:{strategy_key:'same',version_id:'v1',status:'approved',...extra}});
test('selection identity separates scope, strategy and version',()=>{
 assert.notEqual(bulkKey(row()),bulkKey({...row(),scope:'binance'}));
 assert.notEqual(bulkKey(row()),bulkKey(row({version_id:'v2'})));
});
test('bulk PAPER never auto approves, activates or restarts evidence',()=>{
 for(const status of ['analyzed','active','paper_observing','draft','unknown'])assert.equal(bulkDecision(row({status}),'paper').action,undefined);
 for(const status of ['approved','paper_paused','execution_rejected'])assert.equal(bulkDecision(row({status}),'paper').action,'start_paper');
 assert.ok(bulkDecision(row({execution_readiness:{ready:false}}),'paper').reason);
 assert.ok(bulkDecision(row({status:'execution_validated',execution_validation:{mode:'live_observation',passed:true}}),'paper').reason);
});
test('delete forbids execution grants and pause uses only existing stop/deactivate',()=>{
 for(const extra of [{active:true},{paper_observing:true},{status:'active'},{status:'paper_observing'}])assert.ok(bulkDecision(row(extra),'delete').reason);
 assert.equal(bulkDecision(row({active:true}),'pause').action,'deactivate');
 assert.equal(bulkDecision(row({paper_observing:true}),'pause').action,'stop_paper');
 assert.equal(bulkDecision(row(),'delete').action,'delete');
});
test('ZIP has valid CRC, UTF8, safe unique paths and preserves package bytes',()=>{
 const zip=strategyZip([{name:'../전략:1',content:'{"format":"테스트"}'},{name:'../전략:1',content:'two'}]);
 const result=execFileSync(process.env.NOAHAI_QA_PYTHON||(process.platform==='win32'?'python':'python3'),['-c',`import sys,io,zipfile,json
z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read()))
assert z.testzip() is None
print(json.dumps({'names':z.namelist(),'contents':[z.read(n).decode() for n in z.namelist()]}))`],{input:Buffer.from(zip)});
 const data=JSON.parse(result);assert.equal(new Set(data.names).size,2);
 assert(data.names.every(n=>!/[\\/:]/.test(n)&&n.endsWith('.noahstrategy')));
 assert.deepEqual(data.contents,['{"format":"테스트"}','two']);
});
test('ZIP export stays bounded',()=>{
 assert.throws(()=>strategyZip([]));assert.throws(()=>strategyZip(Array.from({length:101},()=>({name:'x',content:'x'}))));
 assert.throws(()=>strategyZip([{name:'x',content:'x'.repeat(EXPORT_LIMIT+1)}]),/20MB/);
});
