const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {prepareRenderer,compatible}=require('../webui/electron/prepare-renderer.cjs');
test('supported Node versions match compiler minimum',()=>{
 for(const v of ['20.20.0','22.11.9','18.20.8'])assert.equal(compatible(v),false);
 for(const v of ['v22.12.0','22.23.1','24.0.0'])assert.equal(compatible(v),true);
});
test('current renderer starts without compilation',async()=>{
 const r=await prepareRenderer('/unused',{isCurrent:()=>true,build:()=>assert.fail('unneeded build')});assert.equal(r.rebuilt,false);
});
test('stale renderer is rebuilt once even with concurrent starts',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-prepare-'));let ready=false,calls=0;
 const options={isCurrent:()=>ready,build:async()=>{calls++;await new Promise(r=>setTimeout(r,30));ready=true;}};
 await Promise.all([prepareRenderer(root,options),prepareRenderer(root,options)]);
 assert.equal(calls,1);assert.equal(fs.existsSync(path.join(root,'.renderer-build.lock')),false);fs.rmSync(root,{recursive:true});
});
test('failed build cleans lock and never launches old renderer',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-failed-'));
 await assert.rejects(prepareRenderer(root,{isCurrent:()=>false,build:async()=>{throw Error('compiler failure');}}),/compiler failure/);
 assert.equal(fs.existsSync(path.join(root,'.renderer-build.lock')),false);
 await assert.rejects(prepareRenderer(root,{isCurrent:()=>false,build:async()=>{}}),/소스가 변경/);fs.rmSync(root,{recursive:true});
});
test('live build lock is never stolen',async()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'noah-busy-'));
 fs.writeFileSync(path.join(root,'.renderer-build.lock'),JSON.stringify({pid:process.pid}));
 await assert.rejects(prepareRenderer(root,{waitMs:0,isCurrent:()=>false,build:()=>assert.fail('no concurrent build')}),/진행 중/);
 assert.equal(fs.existsSync(path.join(root,'.renderer-build.lock')),true);fs.rmSync(root,{recursive:true});
});
