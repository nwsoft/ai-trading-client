const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),Module=require('node:module'),path=require('node:path');
const ts=require(process.env.NOAHAI_QA_TYPESCRIPT||'../webui/node_modules/typescript');
function load(name){const file=path.resolve(__dirname,'../webui/src/'+name),m=new Module(file,module);m._compile(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,file);return m.exports;}
test('feedback filters distinguish inactive, approval and PAPER required without changing execution',()=>{
 const {strategyCatalogView}=load('strategyCatalogView.ts');
 const rows=[{status:'active',active:true},{status:'analyzed'},{status:'needs_clarification'},{status:'approved'},{status:'paper_paused'},{status:'paper_validated',paper_validation:{passed:true}}].map((v,i)=>({...v,name:'fixture'+i,version_id:'v'+i,strategy_key:'k',version:i+1}));
 const groups=[{scope:'unified',strategy_key:'k',versions:rows}],before=JSON.stringify(groups);
 for(const [status,count] of [['inactive',5],['approval',2],['paper_needed',2]])assert.equal(strategyCatalogView(groups,'',status,'name-asc')[0].versions.length,count);
 assert.equal(JSON.stringify(groups),before);
});
test('explicit bulk approval never starts PAPER or activates incomplete/already running versions',()=>{
 const {bulkDecision}=load('strategyBulk.ts');const row=v=>({scope:'unified',version:{status:'analyzed',execution_readiness:{ready:true},...v}});
 assert.equal(bulkDecision(row({}),'approve').action,'approve');
 for(const v of [{status:'needs_clarification'},{active:true},{paper_observing:true},{execution_readiness:{ready:false}}])assert.equal(bulkDecision(row(v),'approve').action,undefined);
});
